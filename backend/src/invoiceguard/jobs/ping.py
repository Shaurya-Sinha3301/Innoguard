"""Dispatch the ping task and print the worker's reply: python -m invoiceguard.jobs.ping"""

from invoiceguard.jobs.tasks import ping

if __name__ == "__main__":
    print(ping.delay().get(timeout=15))
