use std::{
    assert_ne,
    fs::read_to_string,
    io::Write,
    time::{Duration, Instant},
};

use clap::Parser;
use log::{error, warn};
use reqwest::Client;
use tokio::{spawn, sync::mpsc};

const REQ_ISSUE_SLACK_S: f64 = 0.100;
const LATENCY_CUTOFF: f64 = 2.5;

#[derive(Parser, Debug)]
struct Args {
    /// IP address of the trino master node to contact
    #[arg(short, long)]
    master: String,

    /// Port of the trino master to contact
    #[arg(short, long)]
    port: u16,

    /// At the moment assume that we are using the s3data catalog
    /// It should contain a database for each scalefactor 1 to 1000 named tpch_sf<SCALE_FACTOR>
    /// Catalog in the trino database to use
    #[arg(short, long, default_value_t = 1)]
    scale_factor: usize,

    /// Path to the folder containing the query templates
    #[arg(short, long)]
    template_path: String,

    /// Which tpch query to use
    #[arg(short, long)]
    query_number: Option<usize>,

    /// Time for which to run the load latency loop at each load point
    #[arg(short, long)]
    duration: Option<usize>,

    #[arg(long, default_value_t = 1.0)]
    rps: f64,

    /// Number of repetitons for which all queries schould be run
    #[arg(short, long, default_value_t = 1)]
    repetitions: usize,

    /// Number of times to run the query back to back for warm up
    #[arg(short, long, default_value_t = 1)]
    warm_up: usize,
}

async fn query_trino(
    query_number: usize,
    master: &str,
    port: u16,
    client: Client,
    query_vec: &'static [String],
) -> (Duration, serde_json::Value) {
    // to submit a query run a post to /v1/statement
    let post_url = format!("http://{}:{}/v1/statement", master, port);

    let start_time = Instant::now();

    let post = client
        .post(post_url)
        .header("X-Trino-User", "kuchlert")
        .body(query_vec[query_number].as_str())
        .send()
        .await
        .unwrap();
    let mut body = post.json::<serde_json::Value>().await.unwrap();

    // prepare collecting things accross requests
    let mut data_collection = Vec::new();
    if let Some(data) = body.get_mut("data") {
        data_collection.push(data.take());
    }
    let mut query_stats = body.get_mut("stats").unwrap().take();

    let mut next_uri = body
        .get_mut("nextUri")
        .and_then(|option| Some(option.take()));

    // Throw away things we think we don't need
    // body.get_mut("columns").and_then(|o| Some(o.take()));

    while let Some(uri) = next_uri {
        let post = client.get(uri.as_str().unwrap()).send().await.unwrap();
        let mut body = post.json::<serde_json::Value>().await.unwrap();
        if let Some(data) = body.get_mut("data") {
            data_collection.push(data.take());
        }
        if let Some(stats) = body.get_mut("stats") {
            query_stats = stats.take();
        }
        next_uri = body
            .get_mut("nextUri")
            .and_then(|option| Some(option.take()));

        // throw away things we think we don't need
        // body.get_mut("columns").and_then(|o| Some(o.take()));
        // println!("next uri: {}", body);
    }

    let duration = start_time.elapsed();

    // println!("stats collection: {:?}", query_stats);

    (duration, query_stats)
}

#[tokio::main]
async fn main() {
    env_logger::init();

    let args = Args::parse();
    let client = Client::new();

    // template all the queries
    let mut query_vec = Vec::with_capacity(22);
    for query_index in 1..=22 {
        let template =
            read_to_string(format!("{}/q{}.sql", args.template_path, query_index)).unwrap();
        let pattern = regex::Regex::new(r"`DATASET.([a-z]+)`").unwrap();
        let query_string = pattern
            .replace_all(
                &template,
                format!("s3data.tpch_sf{}_ireland.$1", args.scale_factor),
            )
            .trim()
            .trim_end_matches(';')
            .to_string();
        query_vec.push(query_string);
    }
    let query_array: &[String] = Box::leak(query_vec.into_boxed_slice());

    // For debugging run a single query and print the output
    if let Some(query_number) = args.query_number {
        if let Some(loop_duration) = args.duration {
            assert_ne!(0, args.warm_up);
            let mut iteration = 0;
            let baseline_latency = loop {
                let (baseline_latency, _) = query_trino(
                    query_number,
                    &args.master,
                    args.port,
                    client.clone(),
                    query_array,
                )
                .await;
                iteration += 1;
                if iteration == args.warm_up {
                    break baseline_latency;
                }
            };
            // measure load latency curve
            let mut rps = args.rps;
            println!("Baseline latency: {}ms", baseline_latency.as_millis());
            loop {
                println!("Starting with {} rps", rps);
                let iteration_measurements = (rps * (loop_duration as f64)) as usize;
                let rate_slice = Duration::from_secs_f64(1.0 / (rps as f64));
                let master_arc = std::sync::Arc::new(args.master.clone());
                let (measurement_sender, mut measurement_receiver) =
                    mpsc::channel(iteration_measurements);

                let loop_client = client.clone();
                // timing loop for the current load
                tokio::task::spawn_blocking(move || {
                    let mut next = Instant::now();
                    let mut late_counter = 0;
                    for _ in 0..iteration_measurements {
                        next += rate_slice;
                        let sleep_time = Instant::now();
                        let sleep_duration = next.checked_duration_since(sleep_time);
                        let is_late = if let Some(sleep_dur) = sleep_duration {
                            // higher precision than tokio::time::sleep
                            std::thread::sleep(sleep_dur);
                            if let Some(late_time) = sleep_time.checked_duration_since(next) {
                                if late_time.as_secs_f64() > REQ_ISSUE_SLACK_S {
                                    warn!("late after sleeping by: {:?}", late_time);
                                    true
                                } else {
                                    false
                                }
                            } else {
                                false
                            }
                        } else {
                            // late by some time
                            let late_time = sleep_time.duration_since(next);
                            warn!("late on iteraton start by: {:?}", late_time);
                            late_time.as_secs_f64() > REQ_ISSUE_SLACK_S
                        };
                        if is_late {
                            late_counter += 1;
                            if late_counter >= 10 {
                                error!("Timer task late more than 10 times");
                                return;
                            }
                        }
                        // spawn task running the request
                        let task_sender = measurement_sender.clone();
                        let task_master = master_arc.clone();
                        let task_client = loop_client.clone();
                        spawn(async move {
                            let stats = query_trino(
                                query_number - 1,
                                &task_master,
                                args.port,
                                task_client,
                                query_array,
                            )
                            .await;
                            task_sender.send(stats).await.unwrap();
                        });
                    }
                })
                .await
                .unwrap();

                let mut log_file = std::fs::File::create(format!(
                    "/home/ubuntu/trino_load_latency_q{}_sf{}_rps{}.txt",
                    query_number, args.scale_factor, rps
                ))
                .unwrap();
                let mut current_total = 0.0;
                let mut failures = 0;
                while let Some((duration, stats)) = measurement_receiver.recv().await {
                    current_total += duration.as_secs_f64();
                    let state = stats.get("state").unwrap();
                    println!("state: {}, latency: {}ms", state, duration.as_millis());
                    if state == "FAILURE" {
                        failures += 1;
                    }
                    log_file.write(format!("{}\n", stats).as_bytes()).unwrap();
                }
                let current_average = current_total / (iteration_measurements as f64);
                if current_average > LATENCY_CUTOFF * baseline_latency.as_secs_f64() || failures > 0
                {
                    break;
                } else {
                    rps += args.rps;
                }
            }
        } else {
            println!("Executing Query {}", query_number);
            let (duration, stats) = query_trino(
                query_number - 1,
                &args.master,
                args.port,
                client.clone(),
                query_array,
            )
            .await;
            println!(
                "Ran query {}, duration {}ms, stats:\n{:?}",
                query_number,
                duration.as_millis(),
                stats
            )
        }
    } else {
        let mut log_file =
            std::fs::File::create(format!("trino_performance_sf{}.txt", args.scale_factor))
                .unwrap();
        for repetition in 0..args.repetitions {
            for query_number in 0..22 {
                println!(
                    "Starting Repetition {} Query {}",
                    repetition,
                    query_number + 1
                );
                let (duration, stats) = query_trino(
                    query_number,
                    &args.master,
                    args.port,
                    client.clone(),
                    query_array,
                )
                .await;
                log_file
                    .write(
                        format!(
                            "Repetition {}, Query: {}, Duration[us]: {}, Stats:\n{}\n",
                            repetition,
                            query_number + 1,
                            duration.as_micros(),
                            stats
                        )
                        .as_bytes(),
                    )
                    .unwrap();
            }
        }
    }
}
