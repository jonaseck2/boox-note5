"""Wrap the .text of a relocation-free AArch64 ELF object into a minimal static ELF executable."""
import struct, sys
o = open(sys.argv[1], 'rb').read()
shoff, = struct.unpack_from('<Q', o, 0x28); shentsize, shnum, shstrndx = struct.unpack_from('<HHH', o, 0x3a)
secs = [struct.unpack_from('<IIQQQQIIQQ', o, shoff + i * shentsize) for i in range(shnum)]
strtab = secs[shstrndx]
name = lambda s: o[strtab[4] + s[0]:].split(b'\0')[0].decode()
for s in secs:
    if name(s).startswith('.rela'): sys.exit(f'relocations present ({name(s)}); code must be self-contained')
text = next(s for s in secs if name(s) == '.text')
code = o[text[4]:text[4] + text[5]]
base, hdr = 0x400000, 64 + 56
eh = b'\x7fELF' + bytes([2, 1, 1, 0]) + bytes(8) + struct.pack('<HHIQQQIHHHHHH', 2, 183, 1, base + hdr, 64, 0, 0, 64, 56, 1, 0, 0, 0)
ph = struct.pack('<IIQQQQQQ', 1, 5, 0, base, base, hdr + len(code), hdr + len(code), 0x1000)
open(sys.argv[2], 'wb').write(eh + ph + code)
