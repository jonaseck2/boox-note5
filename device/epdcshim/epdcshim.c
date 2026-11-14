// LD_PRELOAD shim for Onyx's vendor composer on a GSI (see docs/runbooks/eink-interface.md).
// A GSI's SurfaceFlinger never sends Onyx's EPDC update list (composer command 0x08020000), so the
// composer never runs its CommitEpdc path and the e-ink panel stays white. v1: call the composer's own
// setEpdcList(display, std::vector<item>) (at vaddr 0x40248 in this exact build, verified by code bytes)
// from a helper thread after frames, with one full-screen entry. v0 raw-prop injection kept behind a prop.
typedef unsigned int u32;
typedef unsigned long long u64;
typedef unsigned long uptr;

struct item { int a, b, c, d, mode; };               // {left, top, right, bottom, mode}, 20 bytes, as parsed by the composer (0x3690c)
struct vec { struct item *begin, *end, *cap; };      // libc++ std::vector layout
struct mxcfb_update_data { u32 top, left, width, height, waveform_mode, update_mode, update_marker; int temp; u32 flags, pad; };
struct plane_res { u32 count_planes; u32 *planes; };
struct obj_props { u32 count_props; u32 *props; u64 *prop_values; };
struct prop_res { u32 prop_id; u32 flags; char name[32]; };

extern void *dlsym(void *, const char *);
extern int __android_log_print(int, const char *, const char *, ...);
extern int __system_property_get(const char *, char *);
extern int atoi(const char *);
extern unsigned long getauxval(unsigned long);
extern int usleep(unsigned int);
extern int pthread_create(void *, const void *, void *(*)(void *), void *);
extern struct plane_res *drmModeGetPlaneResources(int);
extern struct obj_props *drmModeObjectGetProperties(int, u32, u32);
extern struct prop_res *drmModeGetProperty(int, u32);
extern int drmModeAtomicAddProperty(void *, u32, u32, u64);
extern int strcmp(const char *, const char *);
extern int drmPrimeHandleToFD(int, u32, int, int *);
extern void *mmap(void *, unsigned long, int, int, int, long);
extern int munmap(void *, unsigned long);
extern int close(int);
extern int ioctl(int, unsigned long, ...);
extern void *malloc(unsigned long);
extern void free(void *);
extern void *memcpy(void *, const void *, unsigned long);
extern int memcmp(const void *, const void *, unsigned long);
extern void *memset(void *, int, unsigned long);
struct pollfd { int fd; short events, revents; };
extern int poll(struct pollfd *, unsigned long, int);
struct timespec { long tv_sec, tv_nsec; };
extern int clock_gettime(int, struct timespec *);

#define RTLD_NEXT ((void *)-1L)
#define AT_PHDR 3
#define TAG "boox-epdc"
#define SET_EPDC_LIST_VADDR 0x40248u
static const u32 SET_EPDC_LIST_CODE[4] = {0xa9be7bfd, 0xa9014ff4, 0x910003fd, 0x90000000 | 0x3f0 /*adrp x0 masked below*/};

typedef int (*commit_fn)(int, void *, u32, void *);
typedef int (*set_list_fn)(void *, uptr, struct vec *);
static commit_fn real_commit;
static set_list_fn set_list;
static volatile u32 g_frames, g_done;
static u32 g_plane, g_prop_cnt, g_prop_addr, g_probed, g_marker;
static struct mxcfb_update_data g_upd;

static int prop_int(const char *name, int dflt) {
    char v[92] = {0};
    return __system_property_get(name, v) > 0 ? atoi(v) : dflt;
}

/* ---- v2: frame diff -> changed rect only ------------------------------------------------------ */
#define DRM_IOCTL_MODE_ADDFB2 0xC06864B8u
#define DRM_IOCTL_MODE_RMFB   0xC00464AFu
#define DMA_BUF_IOCTL_SYNC    0x40086200u
struct fb_cmd2 { u32 fb_id, width, height, pixel_format, flags, handles[4], pitches[4], offsets[4]; u64 modifier[4]; };
struct fbent { u32 id, handle, pitch, w, h; int dfd; unsigned char *map; };
#define NFB 64
static struct fbent g_fb[NFB];
static int g_drm_fd = -1;
static volatile u32 g_last_fb, g_safe, g_dropped;
static u32 g_fbid_prop, g_fence_prop, g_fb_obj;
#define NPL 32
static u32 g_nplanes, g_pl_obj[NPL], g_pl_fb[NPL], g_pl_fence[NPL];
static int is_fb_prop(u32 obj, u32 prop) {
    for (u32 i = 0; i < g_nplanes; i++) if (g_pl_obj[i] == obj) return g_pl_fb[i] == prop;
    return 0;
}
static int is_fence_prop(u32 obj, u32 prop) {
    for (u32 i = 0; i < g_nplanes; i++) if (g_pl_obj[i] == obj) return g_pl_fence[i] == prop;
    return 0;
}
static unsigned char *g_prev, *g_raw;
static u32 g_prev_w, g_prev_h;
typedef int (*ioctl_fn)(int, unsigned long, void *);
static ioctl_fn real_drm_ioctl;
static int g_lock;
static void lock(void) { while (__atomic_exchange_n(&g_lock, 1, __ATOMIC_ACQUIRE)) usleep(50); }
static void unlock(void) { __atomic_store_n(&g_lock, 0, __ATOMIC_RELEASE); }

int drmIoctl(int fd, unsigned long req, void *arg) {
    if (!real_drm_ioctl) real_drm_ioctl = (ioctl_fn)dlsym(RTLD_NEXT, "drmIoctl");
    int r = real_drm_ioctl(fd, req, arg);
    if (r == 0 && (u32)req == DRM_IOCTL_MODE_ADDFB2) {
        struct fb_cmd2 *c = (struct fb_cmd2 *)arg;
        int dfd = -1;
        if (c->width >= 1872 && drmPrimeHandleToFD(fd, c->handles[0], 0x80000 | 2 /*O_CLOEXEC|O_RDWR: the tone pass writes*/, &dfd)) dfd = -1;
        lock();
        for (int i = 0; i < NFB; i++) if (!g_fb[i].id) {
            g_fb[i].id = c->fb_id; g_fb[i].handle = c->handles[0]; g_fb[i].pitch = c->pitches[0];
            g_fb[i].w = c->width; g_fb[i].h = c->height; g_fb[i].dfd = dfd; g_fb[i].map = 0;
            dfd = -1;
            break;
        }
        unlock();
        if (dfd >= 0) close(dfd);
    } else if ((u32)req == DRM_IOCTL_MODE_RMFB) {
        u32 id = *(u32 *)arg;
        lock();
        for (int i = 0; i < NFB; i++) if (g_fb[i].id == id) {
            if (g_fb[i].map) munmap(g_fb[i].map, (unsigned long)g_fb[i].pitch * g_fb[i].h);
            if (g_fb[i].dfd >= 0) close(g_fb[i].dfd);
            g_fb[i].id = 0;
        }
        unlock();
    }
    return r;
}

static struct fbent *fb_lookup(u32 id) {
    for (int i = 0; i < NFB; i++) if (g_fb[i].id == id) return &g_fb[i];
    return 0;
}

/* ---- v3: tone curve + diff in the commit path ---------------------------------------------------
 * Runs before the real commit, after the buffer's IN_FENCE signalled, so the frame is complete and SF
 * cannot reuse the buffer meanwhile. Every pixel with alpha 0xFF is mapped luma -> g_lut and written
 * back as grey with alpha 0xFE: idempotent, so a buffer SF re-presents from its cache is not mapped
 * twice. The diff runs on the mapped values against the previous mapped frame. */
static unsigned char g_lut[256], g_lutp[256];            // text/UI curve, photo curve
static int g_lut_key = -1;
static volatile int g_pl = 1 << 30, g_pt = 1 << 30, g_pr = -1, g_pb = -1;   // pending rect for the thread

static void fill_lut(unsigned char *lut, int bl, int wh) {
    if (wh <= bl) wh = bl + 1;
    for (int i = 0; i < 256; i++) {
        int v = (i - bl) * 255 / (wh - bl);
        lut[i] = (unsigned char)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
}

static int build_lut(void) {                              // returns 1 when the curves changed
    int bl = prop_int("persist.boox.lut.black", 40), wh = prop_int("persist.boox.lut.white", 235);
    int pb = prop_int("persist.boox.lut.pblack", 16), pw = prop_int("persist.boox.lut.pwhite", 245);
    int key = ((bl * 256 + wh) * 256 + pb) * 256 + pw;
    int adaptive = prop_int("persist.boox.lut.adaptive", 1), pct = prop_int("persist.boox.lut.photo_pct", 35);
    key = key * 31 + adaptive * 1000 + pct + prop_int("persist.boox.lut.bold", 1) * 7;
    if (key == g_lut_key) return 0;
    g_lut_key = key;
    fill_lut(g_lut, bl, wh);
    fill_lut(g_lutp, pb, pw);
    return 1;
}

static inline u32 luma(u32 p) { return (54 * (p & 255) + 183 * ((p >> 8) & 255) + 19 * ((p >> 16) & 255)) >> 8; }

static int process_frame(struct fbent *e, int tone, int *rx, int *ry, int *rr, int *rb) {
    unsigned long sz = (unsigned long)e->pitch * e->h;
    if (!e->map) {
        if (e->dfd < 0) return -1;
        void *m = mmap(0, sz, 1 | 2 /*PROT_READ|PROT_WRITE*/, 1 /*MAP_SHARED*/, e->dfd, 0);
        if (m == (void *)-1L) return -1;
        e->map = (unsigned char *)m;
    }
    u32 w = e->w < 1872 ? e->w : 1872, rowb = e->w * 4;    // panel width; fb is 1920 (virtual)
    int first = 0;
    if (!g_prev || g_prev_w != e->w || g_prev_h != e->h) {   // (re)size BOTH copies together
        free(g_prev); free(g_raw);
        g_prev = (unsigned char *)malloc((unsigned long)rowb * e->h);
        g_raw = (unsigned char *)malloc((unsigned long)rowb * e->h);
        g_prev_w = e->w; g_prev_h = e->h;
        if (!g_prev || !g_raw) { free(g_prev); free(g_raw); g_prev = g_raw = 0; return -1; }
        first = 1;
    }
    if (tone && build_lut() && g_raw) memset(g_raw, 0, (unsigned long)rowb * e->h);   // re-map everything
    struct timespec q0, q1, q2, q3;
    clock_gettime(1, &q0);
    u64 sync = 3 /*READ|WRITE, START*/;
    ioctl(e->dfd, DMA_BUF_IOCTL_SYNC, &sync);
    clock_gettime(1, &q1);
    int x0 = (int)w, x1 = -1, y0 = (int)e->h, y1 = -1;
    /* Content-adaptive tone mapping in bands of B rows / tiles of B px. A tile whose raw pixels are
     * more than photo_pct % mid-grey (luma 48..208) is a photo and gets the gentle curve; text/UI
     * tiles get the strong one. Row status: 0 = equal to the previous mapped frame (skip),
     * 1 = raw equal to the previous raw frame (reuse the mapping), 2 = new raw content (map),
     * 3 = an already-mapped buffer (alpha 0xFE) with different content (diff only, never re-map). */
    enum { B = 32 };
    static u32 band[B][1920];
    static unsigned char st[B], photo[1920 / B + 1];
    int adaptive = prop_int("persist.boox.lut.adaptive", 1), pct = prop_int("persist.boox.lut.photo_pct", 35);
    int bold = prop_int("persist.boox.lut.bold", 1);
    u32 ntiles = (w + B - 1) / B;
    for (u32 yb = 0; yb < e->h; yb += B) {
        u32 nb = e->h - yb < B ? e->h - yb : B;
        int any_new = 0;
        for (u32 r = 0; r < nb; r++) {
            u32 y = yb + r;
            u32 *row = (u32 *)(e->map + (unsigned long)y * e->pitch);
            u32 *pm = (u32 *)(g_prev + (unsigned long)y * rowb);
            u32 *pr = (u32 *)(g_raw + (unsigned long)y * rowb);
            memcpy(band[r], row, w * 4);
            if (!first && !memcmp(band[r], pm, w * 4)) st[r] = 0;
            else if (tone && (band[r][0] >> 24) == 0xFE) st[r] = 3;
            else if (!first && tone && !memcmp(band[r], pr, w * 4)) st[r] = 1;
            else { st[r] = 2; any_new = 1; memcpy(pr, band[r], w * 4); }
        }
        if (tone && any_new) {
            for (u32 t = 0; t < ntiles; t++) photo[t] = 0;
            if (adaptive) {
                for (u32 t = 0; t < ntiles; t++) {
                    u32 xs = t * B, xe = xs + B < w ? xs + B : w, n = 0, mid = 0;
                    for (u32 r = 0; r < nb; r += 2) {
                        const u32 *pr = (const u32 *)(g_raw + (unsigned long)(yb + r) * rowb);
                        for (u32 x = xs; x < xe; x += 2) { u32 l = luma(pr[x]); n++; mid += l >= 48 && l <= 208; }
                    }
                    photo[t] = n && mid * 100 > (u32)pct * n;
                }
            }
        }
        for (u32 r = 0; r < nb; r++) {
            u32 y = yb + r;
            if (st[r] == 0) continue;
            u32 *row = (u32 *)(e->map + (unsigned long)y * e->pitch);
            u32 *pm = (u32 *)(g_prev + (unsigned long)y * rowb);
            u32 *pr = (u32 *)(g_raw + (unsigned long)y * rowb);
            u32 *tmp = band[r];
            if (st[r] == 1) { memcpy(row, pm, w * 4); continue; }   // same content: reuse the mapping
            // State 3: pm is about to hold an OLDER buffer's mapping, so the raw copy no longer matches pm.
            // Invalidate it, or the next fresh frame (raw == pr) would get this stale mapping written back.
            if (st[r] == 3) memset(pr, 0, w * 4);
            if (st[r] == 2 && tone) {
                // Embolden text/UI tiles: the darker of a pixel and its left neighbour, so 1-2 px web and
                // Material strokes grow by 1 px (Chrome ignores Android's Bold text setting). Photos untouched.
                u32 prev = 255;
                for (u32 x = 0; x < w; x++) {
                    u32 v;
                    if (photo[x / B]) { v = g_lutp[luma(pr[x])]; prev = 255; }
                    else {
                        u32 c = g_lut[luma(pr[x])];
                        v = bold && prev < c ? prev : c;
                        prev = c;
                    }
                    tmp[x] = 0xFE000000u | v << 16 | v << 8 | v;
                }
                memcpy(row, tmp, w * 4);
            }
            if (!first && !memcmp(tmp, pm, w * 4)) continue;
            int l = 0, rr = (int)w - 1;
            if (!first) {
                while (l < (int)w && tmp[l] == pm[l]) l++;
                while (rr > l && tmp[rr] == pm[rr]) rr--;
            }
            if (l < x0) x0 = l;
            if (rr > x1) x1 = rr;
            if ((int)y < y0) y0 = (int)y;
            y1 = (int)y;
            memcpy(pm, tmp, w * 4);
        }
    }
    clock_gettime(1, &q2);
    sync = 3 | 4 /*READ|WRITE, END*/;
    ioctl(e->dfd, DMA_BUF_IOCTL_SYNC, &sync);
    clock_gettime(1, &q3);
    {
        static u32 tn;
        if (++tn <= 5 || tn % 50 == 0)
            __android_log_print(4, TAG, "timing sync_start=%ld loop=%ld sync_end=%ld us",
                (q1.tv_sec - q0.tv_sec) * 1000000 + (q1.tv_nsec - q0.tv_nsec) / 1000,
                (q2.tv_sec - q1.tv_sec) * 1000000 + (q2.tv_nsec - q1.tv_nsec) / 1000,
                (q3.tv_sec - q2.tv_sec) * 1000000 + (q3.tv_nsec - q2.tv_nsec) / 1000);
    }
    if (y1 < 0) return 0;
    int pad = prop_int("persist.boox.epdc.pad", 8);
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 >= (int)w) x1 = (int)w - 1;
    if (y1 >= (int)e->h) y1 = (int)e->h - 1;
    x0 &= ~7; y0 &= ~7;                                   // EPDC likes 8-pixel alignment
    *rx = x0; *ry = y0; *rr = x1 + 1; *rb = y1 + 1;
    return 1;
}

static int u_l = 1 << 30, u_t = 1 << 30, u_r = -1, u_b = -1, u_n;   // union of fast updates since last clean
static u32 idle_us;

static void send(int a, int b, int c, int d, int mode) {
    struct item it = {a, b, c, d, mode};
    struct vec v = {&it, &it + 1, &it + 1};
    set_list(0, (uptr)prop_int("persist.boox.epdc.disp", 0), &v);
}

static void *epdc_thread(void *unused) {
    (void)unused;
    struct item it;
    struct vec v;
    for (;;) {
        usleep((u32)prop_int("persist.boox.epdc.period_us", 100000));
        if (!set_list || !prop_int("persist.boox.epdc.enable", 1)) continue;
        static int last_force;
        int force = prop_int("sys.boox.epdc.force", 0);  // bumped after an external full refresh (panel_clean)
        int forced = force != last_force;
        if (g_dropped && g_safe) { g_dropped = 0; forced = 1; }  // redraw what a stripped update skipped
        last_force = force;
        u32 f = g_frames;
        if (f == g_done && !forced && !prop_int("persist.boox.epdc.always", 0)) {
            // idle: after enough fast (non-cleaning) updates, clean their union once with a quality waveform
            idle_us += (u32)prop_int("persist.boox.epdc.period_us", 100000);
            int clean_mode = prop_int("persist.boox.epdc.clean_mode", 16 /* 0x10: full update (partial modes skip unchanged pixels, so they cannot clean) */);
            int clean_after = prop_int("persist.boox.epdc.clean_after", 30);
            if (clean_mode && clean_after > 0 && u_n >= clean_after && u_r >= 0 &&   // 0 = off, and never an empty rect
                idle_us >= (u32)prop_int("persist.boox.epdc.clean_idle_ms", 1500) * 1000u && g_safe) {
                send(u_l, u_t, u_r, u_b, clean_mode);
                __android_log_print(4, TAG, "clean [%d %d %d %d] after %d updates", u_l, u_t, u_r, u_b, u_n);
                u_l = u_t = 1 << 30; u_r = u_b = -1; u_n = 0;
            }
            continue;
        }
        idle_us = 0;
        if (!g_safe) {                                    // see KERNEL PANIC GUARD in drmModeAtomicCommit
            static u32 un;
            if (++un <= 3 || un % 100 == 0) __android_log_print(5, TAG, "skip update: frame not one full-size fb (#%u)", un);
            continue;
        }
        g_done = f;
        it.a = prop_int("persist.boox.epdc.a", 0);
        it.b = prop_int("persist.boox.epdc.b", 0);
        it.c = prop_int("persist.boox.epdc.c", 1872);
        it.d = prop_int("persist.boox.epdc.d", 1404);
        if (!forced && prop_int("persist.boox.epdc.diff", 1) && g_drm_fd >= 0) {
            lock();
            int l = g_pl, t = g_pt, r = g_pr, b = g_pb;
            g_pl = g_pt = 1 << 30; g_pr = g_pb = -1;
            unlock();
            if (r < 0) continue;                          // nothing changed: no update, no flicker
            it.a = l; it.b = t; it.c = r; it.d = b;       // item = {left, top, right, bottom} (kernel logs w=c-a)
        }
        it.mode = prop_int("persist.boox.epdc.list_mode", 2308);  /* 0x904: waveform 4, least flash (camera-measured) */
        if (it.a < u_l) u_l = it.a;
        if (it.b < u_t) u_t = it.b;
        if (it.c > u_r) u_r = it.c;
        if (it.d > u_b) u_b = it.d;
        u_n++;
        v.begin = &it; v.end = &it + 1; v.cap = &it + 1;
        int r = set_list(0, (uptr)prop_int("persist.boox.epdc.disp", 0), &v);
        static u32 n;
        if (++n <= 3 || n % 200 == 0)
            __android_log_print(4, TAG, "setEpdcList #%u -> %d item [%d %d %d %d] mode=%d", n, r, it.a, it.b, it.c, it.d, it.mode);
    }
    return 0;
}

__attribute__((constructor)) static void init(void) {
    uptr base = (uptr)getauxval(AT_PHDR) - 0x40;      // PIE executable: program headers follow the 64-byte ELF header
    const u32 *code = (const u32 *)(base + SET_EPDC_LIST_VADDR);
    if (*(const u32 *)base == 0x464c457f && code[0] == SET_EPDC_LIST_CODE[0] && code[1] == SET_EPDC_LIST_CODE[1] &&
        code[2] == SET_EPDC_LIST_CODE[2] && (code[3] & 0x9f00001f) == 0x90000000) {
        set_list = (set_list_fn)code;
        static char tid[64];
        pthread_create(tid, 0, epdc_thread, 0);
        __android_log_print(4, TAG, "v1: setEpdcList found at %p (base %p)", (void *)code, (void *)base);
    } else {
        __android_log_print(6, TAG, "v1: composer build mismatch at %p, setEpdcList disabled", (void *)code);
    }
}

static void probe(int fd) {
    g_probed = 1;
    struct plane_res *pr = drmModeGetPlaneResources(fd);
    if (!pr) return;
    for (u32 i = 0; i < pr->count_planes && !g_plane; i++) {
        struct obj_props *op = drmModeObjectGetProperties(fd, pr->planes[i], 0xeeeeeeeeu);
        if (!op) continue;
        u32 cnt = 0, addr = 0;
        for (u32 j = 0; j < op->count_props; j++) {
            struct prop_res *p = drmModeGetProperty(fd, op->props[j]);
            if (!p) continue;
            if (!strcmp(p->name, "EPDC_UPDATE_CNT")) cnt = p->prop_id;
            if (!strcmp(p->name, "EPDC_UPDATE_PARMS_ADDR")) addr = p->prop_id;
        }
        if (cnt && addr) { g_plane = pr->planes[i]; g_prop_cnt = cnt; g_prop_addr = addr; }
    }
}

int drmModeAtomicCommit(int fd, void *req, u32 flags, void *user) {
    if (!real_commit) real_commit = (commit_fn)dlsym(RTLD_NEXT, "drmModeAtomicCommit");
    g_frames++;
    if (req) {
        g_drm_fd = fd;
        if (!g_nplanes) {                                 // FB_ID / IN_FENCE_FD have a different prop id per plane
            struct plane_res *pr = drmModeGetPlaneResources(fd);
            for (u32 i = 0; pr && i < pr->count_planes && g_nplanes < NPL; i++) {
                struct obj_props *op = drmModeObjectGetProperties(fd, pr->planes[i], 0xeeeeeeeeu);
                u32 fbp = 0, fep = 0;
                for (u32 j = 0; op && j < op->count_props; j++) {
                    struct prop_res *p = drmModeGetProperty(fd, op->props[j]);
                    if (p && !strcmp(p->name, "FB_ID")) fbp = p->prop_id;
                    if (p && !strcmp(p->name, "IN_FENCE_FD")) fep = p->prop_id;
                }
                if (fbp) { g_pl_obj[g_nplanes] = pr->planes[i]; g_pl_fb[g_nplanes] = fbp; g_pl_fence[g_nplanes] = fep; g_nplanes++; }
            }
            __android_log_print(4, TAG, "planes with FB_ID: %u", g_nplanes);
        }
        struct ritem { u32 obj, prop; u64 val; u32 cursor; };
        struct rreq { u32 cursor, size; struct ritem *items; } *rq = (struct rreq *)req;
        u32 best = 0, best_area = 0, nfb = 0, bw = 0, bh = 0, best_obj = 0;
        for (u32 i = 0; i < rq->cursor; i++) if (rq->items[i].val && is_fb_prop(rq->items[i].obj, rq->items[i].prop)) {
            struct fbent *e = fb_lookup((u32)rq->items[i].val);
            u32 area = e ? e->w * e->h : 0;
            nfb++;
            if (area > best_area) { best_area = area; best = (u32)rq->items[i].val; bw = e->w; bh = e->h; best_obj = rq->items[i].obj; }
        }
        {   // debug: setprop sys.boox.epdc.logcommits N logs the next N commits with their fbs
            static int logged, want_seen;
            int want = prop_int("sys.boox.epdc.logcommits", 0);
            if (want != want_seen) { want_seen = want; logged = 0; }
            if (logged < want) {
                logged++;
                char buf[256]; int o = 0;
                for (u32 i = 0; i < rq->cursor && o < 200; i++) if (is_fb_prop(rq->items[i].obj, rq->items[i].prop)) {
                    struct fbent *e = fb_lookup((u32)rq->items[i].val);
                    (void)e;
                }
                __android_log_print(4, TAG, "commit flags=0x%x items=%u nfb=%u best=%u %ux%u", flags, rq->cursor, nfb, best, bw, bh);
                for (u32 i = 0; i < rq->cursor; i++) if (is_fb_prop(rq->items[i].obj, rq->items[i].prop)) {
                    struct fbent *e = fb_lookup((u32)rq->items[i].val);
                    __android_log_print(4, TAG, "  plane obj=%u fb=%llu %ux%u", rq->items[i].obj, rq->items[i].val, e ? e->w : 0, e ? e->h : 0);
                }
                (void)buf; (void)o;
            }
        }
        if (best) {
            g_last_fb = best;
            g_fb_obj = best_obj;
            // KERNEL PANIC GUARD (2026-11-14): with HW overlays the EPDC read a 704/1216-wide plane as if
            // it were 1872 wide and faulted past its end. Only update when one full-size fb is on screen.
            g_safe = nfb == 1 && bw >= 1872 && bh >= 1404;
            // KERNEL PANIC GUARD v2: the EPDC converts on ANY commit and faults when a narrow plane is on
            // screen. Reject every commit (TEST_ONLY validations included) that is not exactly one
            // full-size fb: SDM's strategy then falls back to GPU composition into one client target.
            if (!(nfb == 1 && bw >= (u32)prop_int("persist.boox.epdc.minw", 1872) && bh >= 1404) && prop_int("persist.boox.epdc.reject", 1)) {
                static u32 rn;
                if (++rn <= 5 || rn % 100 == 0)
                    __android_log_print(5, TAG, "reject commit flags=0x%x nfb=%u largest %ux%u (#%u)", flags, nfb, bw, bh, rn);
                return -22;
            }
            if (g_safe && prop_int("persist.boox.epdc.diff", 1)) {
                int fence = -1;                           // wait for the GPU to finish this frame
                for (u32 i = 0; i < rq->cursor; i++)
                    if (rq->items[i].obj == best_obj && is_fence_prop(rq->items[i].obj, rq->items[i].prop)) fence = (int)(long long)rq->items[i].val;
                if (fence >= 0) { struct pollfd pf = {fence, 1 /*POLLIN*/, 0}; poll(&pf, 1, 100); }
                struct timespec t0, t1;
                clock_gettime(1, &t0);
                lock();
                struct fbent *e = fb_lookup(best);
                int x, y, r, b, d = e ? process_frame(e, prop_int("persist.boox.lut.enable", 1), &x, &y, &r, &b) : -1;
                if (d == 1) {
                    if (x < g_pl) g_pl = x;
                    if (y < g_pt) g_pt = y;
                    if (r > g_pr) g_pr = r;
                    if (b > g_pb) g_pb = b;
                }
                unlock();
                clock_gettime(1, &t1);
                static u32 pn;
                if (++pn <= 5 || pn % 100 == 0)
                    __android_log_print(4, TAG, "frame fb=%u d=%d [%d %d %d %d] %ld us", best, d, x, y, r, b,
                                        (t1.tv_sec - t0.tv_sec) * 1000000 + (t1.tv_nsec - t0.tv_nsec) / 1000);
            }
        }
    }
    if (prop_int("persist.boox.epdc.raw", 0) && req) {   // v0 path, off by default
        if (!g_probed) probe(fd);
        if (g_plane) {
            g_upd.top = 0; g_upd.left = 0;
            g_upd.width = (u32)prop_int("persist.boox.epdc.w", 1872);
            g_upd.height = (u32)prop_int("persist.boox.epdc.h", 1404);
            g_upd.waveform_mode = (u32)prop_int("persist.boox.epdc.wf", 2305);
            g_upd.update_mode = (u32)prop_int("persist.boox.epdc.mode", 1);
            g_upd.update_marker = ++g_marker; g_upd.temp = 0x14; g_upd.flags = 0;
            drmModeAtomicAddProperty(req, g_plane, g_prop_cnt, 1);
            drmModeAtomicAddProperty(req, g_plane, g_prop_addr, (u64)(uptr)&g_upd);
        }
    }
    return real_commit(fd, req, flags, user);
}
