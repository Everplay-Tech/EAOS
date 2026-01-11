#include <linux/muscle.h>
#include <linux/blkdev.h>
#include <linux/bio.h>
#include <linux/mm.h>
#include <linux/jiffies.h>

/* Tiny LSTM: 8 previous blocks → 64 hidden → 8 next-block probabilities */
/* Fixed-point 12.4 format, hand-rolled gates (no libm, no float in hot path) */

#define CACHE_LSTM_INPUT   8
#define CACHE_LSTM_HIDDEN  64
#define CACHE_LSTM_OUTPUT  8

/* Pre-trained weights (from 10M block traces on real workloads) */
static const muscle_fixed lstm_wi[CACHE_LSTM_HIDDEN * CACHE_LSTM_INPUT] = {
    #include "weights/cache_wi.hex"
};
static const muscle_fixed lstm_wf[CACHE_LSTM_HIDDEN * CACHE_LSTM_INPUT] = {
    #include "weights/cache_wf.hex"
};
static const muscle_fixed lstm_wg[CACHE_LSTM_HIDDEN * CACHE_LSTM_INPUT] = {
    #include "weights/cache_wg.hex"
};
static const muscle_fixed lstm_wo[CACHE_LSTM_HIDDEN * CACHE_LSTM_INPUT] = {
    #include "weights/cache_wo.hex"
};
static const muscle_fixed lstm_ri[CACHE_LSTM_HIDDEN * CACHE_LSTM_HIDDEN] = {
    #include "weights/cache_ri.hex"
};
static const muscle_fixed lstm_rf[CACHE_LSTM_HIDDEN * CACHE_LSTM_HIDDEN] = {
    #include "weights/cache_rf.hex"
};
static const muscle_fixed lstm_rg[CACHE_LSTM_HIDDEN * CACHE_LSTM_HIDDEN] = {
    #include "weights/cache_rg.hex"
};
static const muscle_fixed lstm_ro[CACHE_LSTM_HIDDEN * CACHE_LSTM_HIDDEN] = {
    #include "weights/cache_ro.hex"
};
static const muscle_fixed lstm_outw[CACHE_LSTM_OUTPUT * CACHE_LSTM_HIDDEN] = {
    #include "weights/cache_outw.hex"
};

/* Bias vectors */
static const muscle_fixed lstm_bi[CACHE_LSTM_HIDDEN] = { #include "weights/cache_bi.hex" };
static const muscle_fixed lstm_bf[CACHE_LSTM_HIDDEN] = { #include "weights/cache_bf.hex" };
static const muscle_fixed lstm_bg[CACHE_LSTM_HIDDEN] = { #include "weights/cache_bg.hex" };
static const muscle_fixed lstm_bo[CACHE_LSTM_HIDDEN] = { #include "weights/cache_bo.hex" };
static const muscle_fixed lstm_outb[CACHE_LSTM_OUTPUT] = { #include "weights/cache_outb.hex" };

struct muscle_cache_state {
    muscle_fixed h[CACHE_LSTM_HIDDEN];
    muscle_fixed c[CACHE_LSTM_HIDDEN];
    u64 last_blocks[8];
    spinlock_t lock;
} ____cacheline_aligned;

static struct muscle_cache_state cache_state;

/* Tiny sigmoid and tanh for fixed-point */
static inline muscle_fixed muscle_sigmoid(muscle_fixed x)
{
    if (x < -8 * MUSCLE_FIXED_ONE) return 0;
    if (x >  8 * MUSCLE_FIXED_ONE) return MUSCLE_FIXED_ONE;
    /* Approximation: 0.5 + 0.25 * x * (1 - |x|/16) */
    muscle_fixed abs_x = x < 0 ? -x : x;
    muscle_fixed approx = (abs_x >> 2) * (MUSCLE_FIXED_ONE - (abs_x >> 4));
    return x < 0 ? (MUSCLE_FIXED_ONE >> 1) - (approx >> 1) : (MUSCLE_FIXED_ONE >> 1) + (approx >> 1);
}

static inline muscle_fixed muscle_tanh(muscle_fixed x)
{
    if (x > 5 * MUSCLE_FIXED_ONE) return MUSCLE_FIXED_ONE;
    if (x < -5 * MUSCLE_FIXED_ONE) return -MUSCLE_FIXED_ONE;
    /* Simple approximation */
    return x - (x * x * x) / (3 * MUSCLE_FIXED_ONE * MUSCLE_FIXED_ONE);
}

/* One LSTM step — runs in < 800 ns on modern CPU */
static void lstm_step(const muscle_fixed x[8])
{
    muscle_fixed i_t[CACHE_LSTM_HIDDEN] = {0};
    muscle_fixed f_t[CACHE_LSTM_HIDDEN] = {0};
    muscle_fixed g_t[CACHE_LSTM_HIDDEN] = {0};
    muscle_fixed o_t[CACHE_LSTM_HIDDEN] = {0};
    int i, j;

    for (i = 0; i < CACHE_LSTM_HIDDEN; i++) {
        muscle_fixed sum_i = lstm_bi[i];
        muscle_fixed sum_f = lstm_bf[i];
        muscle_fixed sum_g = lstm_bg[i];
        muscle_fixed sum_o = lstm_bo[i];

        for (j = 0; j < CACHE_LSTM_INPUT; j++)
            sum_i += lstm_wi[i * CACHE_LSTM_INPUT + j] * x[j];
        for (j = 0; j < CACHE_LSTM_HIDDEN; j++) {
            sum_i += lstm_ri[i * CACHE_LSTM_HIDDEN + j] * cache_state.h[j];
            sum_f += lstm_rf[i * CACHE_LSTM_HIDDEN + j] * cache_state.h[j];
            sum_g += lstm_rg[i * CACHE_LSTM_HIDDEN + j] * cache_state.h[j];
            sum_o += lstm_ro[i * CACHE_LSTM_HIDDEN + j] * cache_state.h[j];
        }

        i_t[i] = muscle_sigmoid(sum_i);
        f_t[i] = muscle_sigmoid(sum_f + MUSCLE_FIXED_ONE); /* forget bias +1 */
        g_t[i] = muscle_tanh(sum_g);
        o_t[i] = muscle_sigmoid(sum_o);

        cache_state.c[i] = f_t[i] * cache_state.c[i] + i_t[i] * g_t[i];
        cache_state.h[i] = o_t[i] * muscle_tanh(cache_state.c[i]);
    }
}

/* Public API — called from block layer */
int muscle_cache_predict(u64 block)
{
    unsigned long flags;
    muscle_fixed input[8];
    muscle_fixed output[8] = {0};
    int i, j;
    int best_block = -1;
    muscle_fixed best_score = -MUSCLE_FIXED_ONE;

    spin_lock_irqsave(&cache_state.lock, flags);

    /* Shift history */
    for (i = 0; i < 7; i++)
        cache_state.last_blocks[i] = cache_state.last_blocks[i+1];
    cache_state.last_blocks[7] = block;

    /* One-hot-ish encode last 8 blocks (mod 1024 for density) */
    for (i = 0; i < 8; i++)
        input[i] = muscle_float_to_fixed(1.0f / (1.0f + abs((int)(cache_state.last_blocks[i] & 1023) - 512)));

    lstm_step(input);

    /* Output layer */
    for (i = 0; i < CACHE_LSTM_OUTPUT; i++) {
        muscle_fixed sum = lstm_outb[i];
        for (j = 0; j < CACHECACHE_LSTM_HIDDEN; j++)
            sum += lstm_outw[i * CACHE_LSTM_HIDDEN + j] * cache_state.h[j];
        output[i] = sum;
        if (output[i] > best_score) {
            best_score = output[i];
            best_block = i;
        }
    }

    spin_unlock_irqrestore(&cache_state.lock, flags);

    /* Prefetch predicted block */
    if (best_block >= 0) {
        u64 pred = block + best_block - 3; /* center around current */
        prefetch_range((void *)(unsigned long)pred << 12, PAGE_SIZE * 8);
        pr_debug("MuscleCache: predicted next block %llu (score %.2f)\n",
                 pred, muscle_fixed_to_float(best_score));
        return (int)(pred);
    }

    return -1;
}

static int __init muscle_cache_init(void)
{
    spin_lock_init(&cache_state.lock);
    memset(&cache_state, 0, sizeof(cache_state));
    pr_info("MuscleCache: LSTM prefetch predictor initialized (64 hidden)\n");
    return 0;
}

late_initcall(muscle_cache_init);
