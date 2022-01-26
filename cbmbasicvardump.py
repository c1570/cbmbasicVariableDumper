#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dump all variables from a C64 memory dump. Or connect to the
monitor if it is listening to a port.

Further reading:

 * Jim Butterfield, Machine Language for the Commodore 64, 128, and Other Commodore Computers, Prentice Hall Press, 1986.
 * Dan Heeb, Compute!'s VIC20 and Commodore 64 Tool Kit: BASIC, Compute!, 1984.
 * Brückmann, et al, 64 Intern, 7. erweiterte Auflage, Data Becker, 1988.
 * Lothar Englisch, The Advanced Machine Language Book for the Commodore 64, Abacus Software, 1984.
 * https://www.c64-wiki.com/wiki/Floating_point_arithmetic
"""

import struct
import argparse
import socket
import tempfile

class Variable(object):
    """Variable basis class"""
    def __init__(self, data, pos):
        """Construct a variable

        @param data: memory data
        @param pos: position of variable
        """
        self.data = data
        self.pos = pos
        self.name = chr(data[pos] & 0x7f)
        if data[pos + 1] & 0x7f != 0:
            self.name += chr(data[pos + 1] & 0x7f)
    def __str__(self):
        "Convert to string."
        raise NotImplementedError("string converter missing")

class IntegerVariable(Variable):
    "Integer variable, signed 16 bit."
    def __init__(self, data, pos):
        "Constructor"
        Variable.__init__(self, data, pos)
        #Yes, integer variables are stored in big endian.
        self.value = struct.unpack_from(">h", data, pos + 2)[0]
    def __str__(self):
        "Convert to string"
        return "%s%% = %d" % (self.name, self.value)


class FloatVariable(Variable):
    """Floating point variable

    See Compute!'s Toolkit p. 173. Other Information can be found in
    L. Englisch's book on page 3.

    """
    def __init__(self, data, pos):
        "Constructor"
        Variable.__init__(self, data, pos)
        unp = struct.unpack_from("<BBBBB", data, pos + 2)
        exponent = unp[0]
        if exponent == 0:
            mantissa = 0
        else:
            mantissa = unp[1] * 2**(-32)
            mantissa += unp[2] * 2**(-24)
            mantissa += unp[3] * 2**(-16)
            mantissa += (unp[4] | 0x80) * 2**(-8)
            if unp[4] >= 128:
                mantissa *= -1
        self.value = mantissa * 2**(exponent - 128)
    def __str__(self):
        return "%s = %E" % (self.name, self.value)

class ArrayVariable(Variable):
    """Array Variables

    The following data is stored:

     - Two bytes for name (same as for scalars).
     - Total size (little endian uint16).
     - Number of dimensions (uint8).
     - Last dimension (big(!) endian uint16).
     - First dimension (big(!) endian uint16).

    The documentation in [Dan Heeb, Compute!`s VIC20 and Commodore 64
    Tool Kit: BASIC, Compute!, 1984, p. 164] seems to be wrong, the
    elements per dimension are stored in big-endian format!

    """
    def __init__(self, data, pos, dump):
        Variable.__init__(self, data, pos)
        self.dump = dump
        ivarfun = self.data[pos] >= 0x80
        ivarstr = self.data[pos + 1] >= 0x80
        if ivarfun and ivarstr:
            self.tchr = '%'
        elif ivarfun:
            raise NotImplementedError("function")
        elif ivarstr:
            self.tchr = '$'
        else:
            self.tchr = ''
        self.bytes = struct.unpack_from("<H", data, pos + 2)[0]
        self.dim = struct.unpack_from("B", data, pos + 4)[0]
        #Number of elements per dimension from last to first.
        self.nelems = [struct.unpack_from(">H", data, pos + 5 + 2*i)[0] for i in range(self.dim)]
    def __str__(self):
        """Output as a string

        We output the dimensions as they were given in the DIM
        statement.

        """
        nelems = ','.join("%d" % (i - 1) for i in self.nelems)
        res = "%s%s(%s) : %d bytes at $%04X" % (self.name, self.tchr, nelems, self.bytes, self.pos)
        if self.tchr == '$':
            strs = []
            for i in range(0, int((self.bytes - 5 - 2*self.dim)/3)):
                slen, spos = struct.unpack_from("<BH", self.data, self.pos + 5 + 2*self.dim + 3*i)
                value = self.data[spos:spos + slen]
                flag = "*" if spos >= self.dump.fretop else ""
                if flag == "*":
                    self.dump.mark_used(spos, spos + slen)
                strs.append("\"%s\"%s" % (str(value, "ascii", errors="replace"), flag))
            res = f"{res} = [{', '.join(strs)}]"
        return res


class StringVariable(Variable):
    "String variable"
    def __init__(self, data, pos, dump):
        "Constructor"
        Variable.__init__(self, data, pos)
        slen, spos = struct.unpack_from("<BH", data, pos +2)
        begin = spos
        end = spos + slen
        self.pos = (begin, end)
        self.value = self.data[spos:spos + slen]
        self.dump = dump
    def __str__(self):
        "Convert to string for output."
        where = "[$%04X, %d]" % (self.pos[0], self.pos[1] - self.pos[0])
        flag = "*" if self.pos[0] >= self.dump.fretop else ""
        if flag == "*":
            self.dump.mark_used(self.pos[0], self.pos[1])
        return "%s$ %s = \"%s\"%s" % (self.name, where, str(self.value, "ascii", errors="replace"), flag)


class BasicFunction(Variable):
    """A function as defined with DEF FN.

    Figure 1.4.1 in the C64 Intern book seems to be wrong. Jim
    Butterfield's "Machine Language for the Commodore 64" seems to be
    right. The first character has bit 7 set, in the second character
    of the variable name the second bit is cleared for functions.

    The first uin16 (little endian) is a pointer to the definition in
    the basic text.

    """
    def __init__(self, data, pos):
        "Constructor"
        Variable.__init__(self, data, pos)
    def __str__(self):
        "Convert to string for output."
        nam0, nam1, defptr, varptr, unknown = struct.unpack_from("<BBHHB", self.data, self.pos)
        nam0 = chr(nam0 & 0x7f)
        nam1 = chr(nam1 & 0x7f)
        out = "DEF FN %c%c @ $%04X = DEF@$%04x VAR@$%04x $%02x" % (nam0, nam1, self.pos, defptr, varptr, unknown)
        return out


class Dump(object):
    """Helper class to handle dumps."""
    def __init__(self, data):
        """Constructor

        @param data: binary data of dump
        """
        self.data = data
        self.used = bytearray(len(data))
        self.txttab, self.vartab, self.arytab, self.strend, self.fretop, dummy, self.memsiz = struct.unpack_from("<HHHHHHH", data, 0x2b)

    def read_var(self, pos):
        """Read variable from memory

        @param pos: position
        """
        ivarfun = self.data[pos] >= 0x80
        ivarstr = self.data[pos + 1] >= 0x80
        if ivarfun and ivarstr:
            return IntegerVariable(self.data, pos)
        elif ivarfun:
            return BasicFunction(self.data, pos)
        elif ivarstr:
            return StringVariable(self.data, pos, self)
        else:
            return FloatVariable(self.data, pos)

    def mark_used(self, spos, epos):
        for i in range(spos, epos):
            self.used[i] = 1

    def print_heap_garbage(self):
        start = None
        def print_garbage(start, end, data):
            if start is None:
                return
            print("String Heap Garbage [$%04X:$%04X]: \"%s\"" % (start, end, str(data[start:end], "ascii", errors="replace")))
        for i in range(self.fretop, self.memsiz):
            if self.used[i] == 1:
                if start is not None:
                    print_garbage(start, i, self.data)
                    start = None
            else:
                if start is None:
                    start = i
        print_garbage(start, self.memsiz, self.data)


def parse_args():
    """Parse command-line arguments

    @return: Argument parser object
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", help="connect to monitor (url)")
    parser.add_argument("file_names", help="dump file names", nargs='*')
    return parser.parse_args()


def read_socket(sock):
    """Read from socket

    Read until reading blocks.

    @return: read data
    """
    inp = sock.recv(2048)
    while True:
        #print("\"%77s\"" % inp)
        try:
            inp += sock.recv(2048, socket.MSG_DONTWAIT)
        except BlockingIOError:
            break
    return inp


def connect(url):
    """Connect to monitor

    @param url: url to connect to
    @return: file name with dump contents
    """
    #We just need a temporary name...
    tmpf = tempfile.NamedTemporaryFile(delete=False, prefix="c64.",  suffix=".dump")
    host, port = url.split(':')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, int(port)))
        sock.send("r\n".encode())
        read_socket(sock)
        sock.send(('bsave "%s" 0 0000 FFFF\n' % tmpf.name).encode())
        read_socket(sock)
        #We get the registers a second time in order to give the
        #process writing the data enough time. Otherwise we had
        #problems with empty files.
        sock.send("r\n".encode())
        read_socket(sock)
    return tmpf.name


def analyse_dump(fname):
    """Analyse the dump

    @param fname: file name to read dump from
    """
    print("Reading from '%s'." % fname)
    data = open(fname, "rb").read()
    if fname.lower().endswith(".prg"):
        data = data[2:]
    dump = Dump(data)
    print("TXTTAB: Beginning of BASIC program is at $%04x." % dump.txttab)
    print("VARTAB: Variables begin at $%04x." % dump.vartab)
    print("ARYTAB: Array variables begin at $%04x." % dump.arytab)
    print("STREND: Array variables end at $%04x." % dump.strend)
    print("FRETOP: Top of string stack is at $%04x." % dump.fretop)
    print("MEMSIZ: End of string stack is at $%04x." % dump.memsiz)
    print()
    print("Strings postfixed by a * reside in the string stack.")
    print()
    for i in range(dump.vartab, dump.arytab, 7):
        #    print (i, hex(i), data[i:i+8])
        print(dump.read_var(i))
    pos = dump.arytab
    while pos < dump.strend:
        arr = ArrayVariable(dump.data, pos, dump)
        print("%s" % arr)
        pos += arr.bytes
    print()
    dump.print_heap_garbage()


def main(argp):
    """Main function.

    @param argp: argument parser
    """
    if argp.connect is not None:
        fname = connect(argp.connect)
        analyse_dump(fname)
    else:
        for fname in argp.file_names:
            analyse_dump(fname)

if __name__ == "__main__":
    main(parse_args())
