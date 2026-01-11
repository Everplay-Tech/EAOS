#include <linux/muscle.h>
#include <linux/sched.h>
#include <linux/cpumask.h>
#include <linux/random.h>

/* Tiny fixed-point DQN for scheduling (5 processes max per decision) */
#define SCHED_STATES     10    /* remaining + wait time normalized */
#define SCHED_ACTIONS    5
#define SCHED_HIDDEN     32

static const muscle_fixed sched_w1[SCHED_HIDDEN * SCHED_STATES] = {
    /* 32×10 weights — pre-trained offline from 100k episodes */
    #include "weights/sched_w1.hex"
};
static const muscle_fixed sched_b1[SCHED_HIDDEN] = {
    #include "weights/sched_b1.hex"
};
static const muscle_fixed sched_w2[SCHED_ACTIONS * SCHED_HIDDEN] = {
    #include "weights/sched_w2.hex"
};
static const muscle_fixed sched_b2[SCHED_ACTIONS] = {
    #include "weights/sched_b2.hex"
};

static muscle_fixed sched_forward(const muscle_fixed state[SCHED_STATES])
{
    muscle_fixed h[SCHED_HIDDEN] = {0};
    muscle_fixed q[SCHED_ACTIONS] = {0};
    int i, j;

    /* Hidden layer */
    for (i = 0; i < SCHED_HIDDEN; i++) {
        muscle_fixed sum = sched_b1[i];
        for (j = 0; j < SCHED_STATES; j++)
            sum += sched_w1[i * SCHED_STATES + j] * state[j];
        h[i] = muscle_relu(sum);
    }

    /* Output Q-values */
    for (i = 0; i < SCHED_ACTIONS; i++) {
        muscle_fixed sum = sched_b2[i];
        for (j = 0; j < SCHED_HIDDEN; j++)
            sum += sched_w2[i * SCHED_HIDDEN + j] * h[j];
        q[i] = sum;
    }

    /* Return best action */
    muscle_fixed best = q[0];
    int action = 0;
    for (i = 1; i < SCHED_ACTIONS; i++) {
        if (q[i] > best) {
            best = q[i];
            action = i;
        }
    }
    return action;
}

/* Called from pick_next_task() path */
void muscle_scheduler_tick(struct rq *rq)
{
    struct task_struct *candidates[5];
    muscle_fixed state[SCHED_STATES];
    int i, n = 0;

    /* Collect up to 5 runnable tasks */
    struct task_struct *p, *next;
    rq_lock(rq, NULL);
    list_for_each_entry_safe(p, next, &rq->cfs_tasks, tasks) {
        if (n < 5) candidates[n++] = p;
    }

    if (n == 0) {
        rq_unlock(rq, NULL);
        return;
    }

    /* Build state vector: remaining vruntime + wait time */
    for (i = 0; i < n; i++) {
        state[i] = muscle_float_to_fixed((float)candidates[i]->se.vruntime / 1000000.0f);
        state[i + 5] = muscle_float_to_fixed((float)(jiffies - candidates[i]->se.last_ran) / 100.0f);
    }
    for (; i < 5; i++) {
        state[i] = 0;
        state[i + 5] = 0;
    }

    int chosen = sched_forward(state);
    if (chosen < n && candidates[chosen] != rq->curr) {
        pr_info("MuscleScheduler: chose pid %d (Q-est %.2f)\n",
                candidates[chosen]->pid,
                muscle_fixed_to_float(sched_forward(state)));
        rq->curr = candidates[chosen];
    }

    rq_unlock(rq, NULL);
}
