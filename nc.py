#!/usr/bin/python

#
# starting code taken from:
# http://4thmouse.com/index.php/2008/02/22/netcat-clone-in-three-languages-part-ii-python/
# 
# added async io on stdin and stdout to improve performance
# tested as proxy command for SSH when the regular netcat is not available
#

from optparse import OptionParser
import os
import sys
import socket
import select
import fcntl
import time


def stderr_emitter(*msg):
    for m in msg:
        sys.stderr.write(str(m))
    sys.stderr.write("\n")
    sys.stderr.flush()


def debug_emitter(*msg):
    stderr_emitter("DEBUG: ", *msg)


debug = debug_emitter
errout = stderr_emitter


def set_non_blocking(fd):
    """Make a fd non-blocking."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    flags = flags | os.O_NONBLOCK
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)


class NetCatError(Exception):
    pass


class UnbufferedNonBlockingStream(object):
    def __init__(self, file_object):
        self.fds = file_object.fileno()
        self.fd = os.dup(self.fds)
        set_non_blocking(self.fd)

    def fileno(self):
        return self.fd

    def read(self, count):
        return os.read(self.fd, count)

    def write(self, data):
        total = 0
        WRITE_SIZE = 4096
        while total < len(data):
            r, w, x = select.select([], [self.fd], [self.fd])
            if x:
                raise NetCatError("ERROR: writing to pipe: %d" % self.fd)
            block = data[total:total+WRITE_SIZE]
            written = os.write(self.fd, block)
            debug("wrote to %d(%d): %d bytes [%d/%d]: %s" % (self.fd, self.fds, written, total, len(data), block[:written].encode("hex")))
            total += written

    def flush(self):
        pass

    def close(self):
        os.close(self.fd)

    def __del__(self):
        self.close()


class NetTool(object):
    def __init__(self):
        self.connect = None
        self.hostname = None
        self.port = None
        self.socket = None
        self.stdin = None
        self.stdout = None

    def run(self):
        self.parse_options()
        self.reopen_standards()
        self.connect_socket()
        try:
            self.forward_data()
        except NetCatError, e:
            errout("ERROR: %s" % str(e))

    def parse_options(self):
        global debug

        parser = OptionParser(usage="usage: %prog [options]")

        parser.add_option("-d", "--debug",
                          action="store_true",
                          dest="debug",
                          help="Enables debugging")

        parser.add_option("-c", "--connect",
                          action="store_true",
                          dest="connect",
                          help="Connect to a remote host")

        parser.add_option("-l", "--listen",
                          action="store_false",
                          dest="connect",
                          help="Listen for a remote host to connect to self host")

        parser.add_option("-r",
                          "--remote-host",
                          action="store",
                          type="string",
                          dest="hostname",
                          help="Specify the host to connect to")

        parser.add_option("-p",
                          "--port",
                          action="store",
                          type="int",
                          dest="port",
                          help="Specify the TCP port")

        parser.set_defaults(connect=None, hostname=None)
        (options, args) = parser.parse_args();

        if options.connect is None:
            sys.stdout.write("no connection type specified\n")
            parser.print_help()
            sys.exit()

        if options.port is None:
            sys.stdout.write("no port specified\n")
            parser.print_help()
            sys.exit()

        if not (not options.connect or not (options.hostname is None)):
            sys.stdout.write("connect type requires a hostname\n")
            parser.print_help()
            sys.exit()

        if not options.debug:
            debug = lambda msg: None
        else:
            debug("debugging enabled")

        self.connect = options.connect
        self.hostname = options.hostname
        self.port = options.port

    def connect_socket(self):
        if self.connect:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.hostname, self.port))
        else:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.setsockopt(socket.SOL_SOCKET, socket.TCP_NODELAY, 1)
            except socket.error:
                errout("Warning: unable to set TCP_NODELAY...")
            server.bind(('localhost', self.port))
            server.listen(1)
            self.socket, address = server.accept()
        self.socket.setblocking(0)

    def forward_data(self):
        select_ready = select.select
        conn_socket = self.socket
        socket_recv = self.socket.recv
        socket_sendall = self.socket.sendall
        stdout_write = self.stdout.write
        stdout_flush = self.stdout.flush
        stdin = self.stdin
        stdin_read = self.stdin.read
        BLOCK_SIZE = 16384
        while 1:
            debug("waiting for read ready...")
            read_ready, write_ready, in_error = select_ready([conn_socket, stdin], [], [conn_socket, stdin], 1)
            debug("%s, %s, %s" % (read_ready, write_ready, in_error))
            if in_error:
                raise NetCatError("select error")
            for read_fd in read_ready:
                if read_fd is conn_socket:
                    try:
                        buf = socket_recv(BLOCK_SIZE)
                        if not buf:
                            conn_socket.close()
                            conn_socket.shutdown()
                            return
                        stdout_write(buf)
                        stdout_flush()
                        debug("read from remote %d bytes" % len(buf))
                    except socket.error, e:
                        print e
                if read_fd is stdin:
                    block = stdin_read(BLOCK_SIZE)
                    if not block:
                        return
                    try:
                        socket_sendall(block)
                    except socket.error:
                        conn_socket.close()
                        conn_socket.shutdown()
                        raise NetCatError("send failed, connection closed by remote")
                    debug("sent to remote %d bytes" % len(block))

    def reopen_standards(self):
        self.stdin = UnbufferedNonBlockingStream(sys.stdin)
        sys.stdin.close()
        self.stdout = UnbufferedNonBlockingStream(sys.stdout)
        sys.stdout.close()


tool = NetTool()
tool.run()
