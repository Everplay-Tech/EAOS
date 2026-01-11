#ifndef _LINUX_MUSCLE_H
#define _LINUX_MUSCLE_H

#include <linux/types.h>
#include <linux/spinlock.h>
#include <linux/sched.h>

#define MUSCLE_FIXED_SHIFT 12
#define MUSCLE_FIXED_ONE (1 << MUSCLE_FIXED_SHIFT)

typedef s32 muscle_fixed;

/* Tiny fixed-point neural net utilities */
static inline muscle_fixed muscle_float_to_fixed(float x)
{
	return (muscle_fixed)(x * MUSCLE_FIXED_ONE);
}

static inline float muscle_fixed_to_float(muscle_fixed x)
{
	return (float)x / MUSCLE_FIXED_ONE;
}

/* Common weights (baked in — trained offline) */
extern const muscle_fixed muscle_sine_weights[40*40 + 40*40 + 40*1 + 40 + 40 + 1];

/* Core muscle APIs */
void muscle_scheduler_tick(struct rq *rq);
int muscle_cache_predict(u64 block);
void muscle_security_check(u64 syscall_nr, u64 arg1, u64 arg2);
void muscle_io_predict(struct request_queue *q, struct request *rq);
int muscle_compress(void *dst, size_t *dstlen, const void *src, size_t srclen);
int muscle_decompress(void *dst, size_t *dstlen, const void *src, size_t srclen);
void muscle_grid_walk(struct path *path);
float muscle_sine_predict(float x);

#endif /* _LINUX_MUSCLE_H */
