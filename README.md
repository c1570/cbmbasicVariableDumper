# Commodore Basic V2 Variable Dumper

This tool dumps the current run-time variables of a basic program. It
uses a memory dump for this purpose or it can connect to the vice
monitor via a socket.

For further information visit:

	https://v2.pikacode.com/pararaum/cbmbasicVariableDumper

# Usage

## Reading a memory dump

A memory dump of a C64 should contain at least the addresses $0000 to
$9fff.  For example:

```
cbmbasicvardump.py memory.dump
```

This will try to read all the variables which where defined at the
momemt the dump was created.

## Connect to vice

Vice (x64) must be running and the option "Enable remote monitor
server" must be enabled. Then issueing a

```
cbmbasicvardump.py --connect localhost:6510
```

will create a dump in the temporary directory for your convenience
called "c64.XXXXXXX.dump" and immediately dump all variables.

