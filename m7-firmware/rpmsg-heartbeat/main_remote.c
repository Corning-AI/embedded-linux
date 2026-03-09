/*
 * RPMsg Heartbeat — Cortex-M7 FreeRTOS firmware for i.MX8MP
 *
 * Based on NXP's rpmsg_lite_str_echo_rtos example from:
 *   mcux-sdk-examples/boards/evkmimx8mp/multicore_examples/
 *
 * What this firmware does:
 *   1. Initializes RPMsg-Lite on the M7 side
 *   2. Waits for Linux (A53) to create the RPMsg channel
 *   3. Sends "HB:<count>:<uptime_ms>" heartbeat every 1 second
 *   4. Echoes back any messages received from Linux (for ping/pong testing)
 *
 * The A53 side sees this as /dev/ttyRPMSG0 after loading the firmware:
 *   echo start > /sys/class/remoteproc/remoteproc0/state
 *   cat /dev/ttyRPMSG0   # see heartbeat messages
 *   echo "ping" > /dev/ttyRPMSG0  # get "echo: ping" back
 *
 * Build (on Linux host with ARM GCC + MCUXpresso SDK):
 *   cd mcux-sdk-examples/boards/evkmimx8mp/multicore_examples/rpmsg_lite_str_echo_rtos/armgcc
 *   # Replace main_remote.c with this file
 *   export ARMGCC_DIR=/opt/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi
 *   ./build_release.sh
 *
 * Memory map (i.MX8MP):
 *   0x40000000..0x4001FFFF  —  M7 TCM (128 KB, fast local SRAM)
 *   0x55000000..0x550FFFFF  —  Reserved DRAM for M7 code (set in device tree)
 *   0x55800000..0x5580FFFF  —  Shared memory for RPMsg VirtIO rings
 */

#include <stdio.h>
#include <string.h>

#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

#include "rpmsg_lite.h"
#include "rpmsg_queue.h"
#include "rpmsg_ns.h"

#include "board.h"
#include "fsl_debug_console.h"
#include "pin_mux.h"
#include "clock_config.h"

/*******************************************************************************
 * Definitions
 ******************************************************************************/

/* RPMsg channel name — must match Linux device tree rpmsg node */
#define RPMSG_CHANNEL_NAME "rpmsg-virtual-tty-channel-1"

/* Shared memory region for VirtIO rings (must match Linux reserved-memory) */
#define VDEV0_VRING_BASE   0x55000000U
#define VDEV0_VRING_SIZE   0x8000U

/* Heartbeat interval */
#define HEARTBEAT_INTERVAL_MS  1000

/* Task stack sizes */
#define APP_TASK_STACK_SIZE   (256U)

/*******************************************************************************
 * Globals
 ******************************************************************************/

static struct rpmsg_lite_instance   *volatile g_rpmsg;
static struct rpmsg_lite_endpoint   *volatile g_ept;
static rpmsg_queue_handle            g_queue;
static volatile uint32_t             g_remote_addr;
static SemaphoreHandle_t             g_channel_ready;

/*******************************************************************************
 * Name service callback — called when Linux announces the channel
 ******************************************************************************/

static void ns_new_ept_cb(uint32_t new_ept, const char *new_ept_name, uint32_t flags, void *user_data)
{
    /* Linux has created its endpoint; save the address */
    g_remote_addr = new_ept;
    xSemaphoreGive(g_channel_ready);
}

/*******************************************************************************
 * Heartbeat task — sends periodic status to Linux
 ******************************************************************************/

static void heartbeat_task(void *param)
{
    char buf[64];
    uint32_t count = 0;

    /* Wait for the RPMsg channel to be established */
    PRINTF("M7: waiting for Linux RPMsg channel...\r\n");
    xSemaphoreTake(g_channel_ready, portMAX_DELAY);
    PRINTF("M7: channel ready (remote addr=%d)\r\n", g_remote_addr);

    for (;;)
    {
        /* Format: "HB:<count>:<uptime_ms>" */
        uint32_t uptime_ms = xTaskGetTickCount() * portTICK_PERIOD_MS;
        int len = snprintf(buf, sizeof(buf), "HB:%lu:%lu", count, uptime_ms);

        rpmsg_lite_send(g_rpmsg, g_ept, g_remote_addr, buf, len, RL_BLOCK);

        count++;
        vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_INTERVAL_MS));
    }
}

/*******************************************************************************
 * Echo task — echoes any messages received from Linux
 ******************************************************************************/

static void echo_task(void *param)
{
    char rx_buf[256];
    char tx_buf[280];
    uint32_t rx_len;
    uint32_t src_addr;

    /* Wait for channel */
    xSemaphoreTake(g_channel_ready, portMAX_DELAY);
    /* Give semaphore back so heartbeat_task can also proceed */
    xSemaphoreGive(g_channel_ready);

    PRINTF("M7: echo task running\r\n");

    for (;;)
    {
        /* Blocking receive */
        if (rpmsg_queue_recv(g_rpmsg, g_queue, &src_addr,
                             rx_buf, sizeof(rx_buf) - 1, &rx_len,
                             RL_BLOCK) == RL_SUCCESS)
        {
            rx_buf[rx_len] = '\0';
            PRINTF("M7: rx '%s' from addr %d\r\n", rx_buf, src_addr);

            /* Echo back with prefix */
            int len = snprintf(tx_buf, sizeof(tx_buf), "echo: %s", rx_buf);
            rpmsg_lite_send(g_rpmsg, g_ept, src_addr, tx_buf, len, RL_BLOCK);
        }
    }
}

/*******************************************************************************
 * Main task — initializes RPMsg and spawns worker tasks
 ******************************************************************************/

static void app_task(void *param)
{
    PRINTF("\r\n");
    PRINTF("===========================================\r\n");
    PRINTF("  i.MX8MP M7 RPMsg Heartbeat (FreeRTOS)\r\n");
    PRINTF("===========================================\r\n");

    g_channel_ready = xSemaphoreCreateBinary();

    /*
     * Initialize RPMsg as REMOTE.
     *
     * On i.MX8MP, the M7 is the "remote" processor.
     * Linux (A53) is the "master" and manages the VirtIO rings.
     * We pass the shared memory base address so RPMsg-Lite knows
     * where to find the VirtIO descriptor rings set up by Linux.
     */
    g_rpmsg = rpmsg_lite_remote_init(
        (void *)VDEV0_VRING_BASE,
        RPMSG_LITE_LINK_ID,
        RL_NO_FLAGS
    );
    PRINTF("M7: RPMsg initialized (vring @ 0x%08X)\r\n", VDEV0_VRING_BASE);

    /* Create receive queue and endpoint */
    g_queue = rpmsg_queue_create(g_rpmsg);
    g_ept   = rpmsg_lite_create_ept(g_rpmsg, RL_ADDR_ANY, rpmsg_queue_rx_cb, g_queue);

    /* Announce our endpoint to Linux via name service */
    rpmsg_ns_announce(g_rpmsg, g_ept, RPMSG_CHANNEL_NAME, RL_NS_CREATE);
    PRINTF("M7: announced channel '%s'\r\n", RPMSG_CHANNEL_NAME);

    /* Spawn worker tasks */
    xTaskCreate(heartbeat_task, "heartbeat", APP_TASK_STACK_SIZE, NULL, 3, NULL);
    xTaskCreate(echo_task,      "echo",      APP_TASK_STACK_SIZE, NULL, 4, NULL);

    /* This task is no longer needed */
    vTaskDelete(NULL);
}

/*******************************************************************************
 * Entry point
 ******************************************************************************/

int main(void)
{
    /* Board-specific init (clocks, pins, debug UART) */
    BOARD_InitMemory();
    BOARD_RdcInit();
    BOARD_InitBootPins();
    BOARD_BootClockRUN();
    BOARD_InitDebugConsole();

    /*
     * Copy resource table to shared memory.
     * The resource table tells Linux about our VirtIO rings.
     * This is handled by the linker script and startup code in the
     * NXP SDK — see the .ld file for RPMSG_SH_MEM section.
     */
    copyResourceTable();

    /* Create the main application task */
    xTaskCreate(app_task, "app", APP_TASK_STACK_SIZE * 2, NULL, tskIDLE_PRIORITY + 1, NULL);

    /* Start FreeRTOS scheduler — never returns */
    vTaskStartScheduler();

    /* Should never reach here */
    for (;;) {}
}
