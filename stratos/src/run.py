########### DO NOT DELETE ###########
import subprocess
import sys


def main():
    exit_code = subprocess.run(["python", "solution.py"])
    sys.exit(exit_code)


# make testable for build to pass
def startup():
    if __name__ == '__main__':
        main()


startup()

########### DO NOT DELETE ###########
