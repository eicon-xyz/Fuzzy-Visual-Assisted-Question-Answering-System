"""Check if a TCP port is available for binding on the given host."""
import socket
import sys


def is_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/check_port.py <host> <port>", file=sys.stderr)
        sys.exit(2)

    host = sys.argv[1]
    try:
        port = int(sys.argv[2])
    except ValueError:
        print(f"Invalid port: {sys.argv[2]}", file=sys.stderr)
        sys.exit(2)

    if is_port_available(host, port):
        sys.exit(0)

    print(
        f"[HAJIMI] Port {port} on {host} is not available "
        f"(in use or blocked by system)."
    )
    print(f"  Check: netstat -ano | findstr :{port}")
    print(f"  Or try: set HAJIMI_PORT={port + 1} && scripts\\start_server.bat")
    sys.exit(1)


if __name__ == "__main__":
    main()
