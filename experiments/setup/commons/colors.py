class ConsoleColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    GRAY = '\033[90m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'

def print_error(msg):
    print(ConsoleColors.FAIL + msg + ConsoleColors.ENDC)

def print_info(msg):
    print(ConsoleColors.OKCYAN + msg + ConsoleColors.ENDC)

def print_debug(msg):
    print(ConsoleColors.GRAY + ConsoleColors.ITALIC + msg + ConsoleColors.ENDC)
