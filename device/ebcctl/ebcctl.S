// ebcctl <int>: ioctl(open("/dev/ebc", O_RDWR), 0x700b, &int). Exit code: ioctl result (0 = ok).
// Syscall-only, no libc. Reverse-engineered from SurfaceFlinger on Boox Note5 (see docs/runbooks/eink-interface.md).
    .text
    .globl _start
_start:
    ldr     x9, [sp]            // argc
    mov     w3, #-1             // default: -1 (no forced waveform)
    cmp     x9, #2
    b.lt    1f
    ldr     x1, [sp, #16]       // argv[1]
    mov     w3, #0
    mov     w4, #1              // sign
    ldrb    w2, [x1]
    cmp     w2, #'-'
    b.ne    2f
    mov     w4, #-1
    add     x1, x1, #1
2:  ldrb    w2, [x1], #1
    cbz     w2, 3f
    sub     w2, w2, #'0'
    mov     w5, #10
    madd    w3, w3, w5, w2
    b       2b
3:  mul     w3, w3, w4
1:  sub     sp, sp, #16
    str     w3, [sp]
    mov     x0, #-100           // AT_FDCWD
    adr     x1, path
    mov     x2, #2              // O_RDWR
    mov     x3, #0
    mov     x8, #56             // openat
    svc     #0
    cmp     x0, #0
    b.lt    9f
    mov     x10, x0
    mov     x1, #0x700b
    mov     x2, sp
    mov     x8, #29             // ioctl
    svc     #0
9:  neg     x0, x0
    mov     x8, #93             // exit
    svc     #0
path:
    .asciz  "/dev/ebc"
