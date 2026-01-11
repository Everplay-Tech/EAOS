#include <linux/muscle.h>
#include <linux/syscalls.h>
#include <linux/uaccess.h>
#include <linux/sched.h>
#include <linux/random.h>

/* 64 → 16 → 64 autoencoder for syscall + 6 args vector */
#define SEC_INPUT  7
#define SEC_HIDDEN 16

static const muscle_fixed sec_enc_w[SEC_HIDDEN * SEC_INPUT] = { #include "weights/sec_enc_w.hex" };
static const muscle_fixed sec_enc_b[SEC_HIDDEN] = { #include "weights/sec_enc_b.hex" };
static const muscle_fixed sec_dec_w[SEC_INPUT * SEC_HIDDEN] = { #include "weights/sec_dec_w.hex" };
static const muscle_fixed sec_dec_b[SEC_INPUT] = { #include "weights/sec_dec_b.hex" };

static muscle_fixed sec_running_mean[SEC_INPUT];
static muscle_fixed sec_running_var[SEC_INPUT];
static u64 sec_count = 0;

static inline muscle_fixed sec_forward(const muscle_fixed x[SEC_INPUT], muscle_fixed h[SEC_HIDDEN])
{
    int i, j;
    for (i = 0; i < SEC_HIDDEN; i++) {
        muscle_fixed sum = sec_enc_b[i];
        for (j = 0; j < SEC_INPUT; j++)
            sum += sec_enc_w[i * SEC_INPUT + j] * x[j];
        h[i] = muscle_relu(sum);
    }
    return 0;
}

static inline muscle_loss(const muscle_fixed x[SEC_INPUT], const muscle_fixed h[SEC_HIDDEN])
{
    muscle_fixed recon[SEC_INPUT] = {0};
    muscle_fixed loss = 0;
    int i, j;

    for (i = 0; i < SEC_INPUT; i++) {
        muscle_fixed sum = sec_dec_b[i];
        for (j = 0; j < SEC_HIDDEN; j++)
            sum += sec_dec_w[i * SEC_HIDDEN + j] * h[j];
        recon[i] = sum;
        muscle_fixed diff = x[i] - recon[i];
        loss += diff * diff;
    }
    return loss;
}

void muscle_security_check(u64 syscall_nr, u64 arg1, u64 arg2)
{
    muscle_fixed input[7] = {
        muscle_float_to_fixed((float)syscall_nr / 400.0f),
        muscle_float_to_fixed((float)arg1 / 1e12f),
        muscle_float_to_fixed((float)arg2 / 1e12f),
        muscle_float_to_fixed((float)current->pid / 32768.0f),
        muscle_float_to_fixed((float)jiffies / 100000.0f),
        muscle_float_to_fixed((float)current_uid().val / 65536.0f),
        muscle_float_to_fixed((float)get_random_u32() / UINT_MAX)
    };
    muscle_fixed h[SEC_HIDDEN];

    sec_forward(input, h);
    muscle_fixed err = sec_forward_loss(input, h);

    /* Online mean/variance update */
    sec_count++;
    for (int i = 0; i < SEC_INPUT; i++) {
        muscle_fixed delta = input[i] - sec_running_mean[i];
        sec_running_mean[i] += delta / sec_count;
        sec_running_var[i] += delta * (input[i] - sec_running_mean[i]);
    }

    muscle_fixed std = sec_running_var[0] / (sec_count > 1 ? sec_count - 1 : 1);
    if (std > 0 && err > 16 * std) {  /* 4σ threshold */
        pr_alert("MuscleSecurity: ANOMALY pid=%d syscall=%llu err=%.2f → KILL\n",
                 current->pid, syscall_nr, muscle_fixed_to_float(err));
        force_sig(SIGKILL, current);
    }
}

static int __init muscle_security_init(void)
{
    pr_info("MuscleSecurity: autoencoder anomaly detector active\n");
    return 0;
}

late_initcall(muscle_security_init);
