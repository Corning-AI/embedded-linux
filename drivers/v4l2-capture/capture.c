// SPDX-License-Identifier: GPL-2.0
/*
 * capture.c — V4L2 camera frame capture for i.MX8MP
 *
 * Demonstrates the V4L2 (Video for Linux 2) userspace API:
 *   1. Open video device and query capabilities
 *   2. Set capture format (resolution, pixel format)
 *   3. Request and mmap kernel buffers (zero-copy capture)
 *   4. Queue buffers, start streaming, dequeue filled frames
 *   5. Save raw frame to file
 *
 * This is the SAME API that GStreamer's v4l2src uses internally.
 * Understanding it helps you debug camera pipelines at a lower level
 * than GStreamer abstracts away.
 *
 * Build:
 *   $CC -o capture capture.c    (CC = aarch64-poky-linux-gcc for cross)
 *
 * Usage on EVK:
 *   ./capture                          # defaults: /dev/video3, 640x480
 *   ./capture /dev/video3 1920 1080    # 1080p capture
 *
 * i.MX8MP video device map:
 *   /dev/video0  VPU encoder (H.264/HEVC)
 *   /dev/video1  VPU decoder
 *   /dev/video2  ISI memory-to-memory (color conversion)
 *   /dev/video3  ISI capture ← camera frames arrive here
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>   /* V4L2 API: VIDIOC_*, v4l2_* structs */

#define NUM_BUFFERS 4

struct buffer {
	void   *start;     /* mmap'd pointer to kernel buffer */
	size_t  length;    /* buffer size in bytes */
};

/*
 * xioctl — ioctl wrapper with EINTR retry.
 *
 * V4L2 ioctls can be interrupted by signals (EINTR). The standard
 * practice is to retry. This is a common pattern in systems programming.
 */
static int xioctl(int fd, unsigned long request, void *arg)
{
	int r;
	do {
		r = ioctl(fd, request, arg);
	} while (r == -1 && errno == EINTR);
	return r;
}

int main(int argc, char *argv[])
{
	const char *dev = argc > 1 ? argv[1] : "/dev/video3";
	int width  = argc > 2 ? atoi(argv[2]) : 640;
	int height = argc > 3 ? atoi(argv[3]) : 480;

	struct buffer buffers[NUM_BUFFERS];
	int fd, i;

	/*
	 * Step 1: Open the video device.
	 *
	 * O_RDWR is required for capture (we read frames) and format setting.
	 * O_NONBLOCK would make DQBUF return immediately if no frame ready.
	 */
	fd = open(dev, O_RDWR);
	if (fd < 0) {
		perror("open video device");
		return 1;
	}
	printf("Opened %s\n", dev);

	/*
	 * Step 2: Query device capabilities.
	 *
	 * VIDIOC_QUERYCAP tells us what this device can do.
	 * We need V4L2_CAP_VIDEO_CAPTURE_MPLANE (multi-planar capture)
	 * because i.MX8MP ISI uses the multi-planar API.
	 */
	struct v4l2_capability cap;
	if (xioctl(fd, VIDIOC_QUERYCAP, &cap) < 0) {
		perror("VIDIOC_QUERYCAP");
		close(fd);
		return 1;
	}
	printf("Driver:  %s\n", cap.driver);
	printf("Card:    %s\n", cap.card);
	printf("Caps:    0x%08x", cap.capabilities);
	if (cap.capabilities & V4L2_CAP_VIDEO_CAPTURE)
		printf(" [CAPTURE]");
	if (cap.capabilities & V4L2_CAP_VIDEO_CAPTURE_MPLANE)
		printf(" [CAPTURE_MPLANE]");
	if (cap.capabilities & V4L2_CAP_STREAMING)
		printf(" [STREAMING]");
	printf("\n");

	/*
	 * Determine buffer type: single-planar or multi-planar.
	 * i.MX8MP ISI uses MPLANE. Older/simpler devices use single-plane.
	 */
	enum v4l2_buf_type buf_type;
	if (cap.capabilities & V4L2_CAP_VIDEO_CAPTURE_MPLANE)
		buf_type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
	else
		buf_type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

	/*
	 * Step 3: Set the capture format.
	 *
	 * For MPLANE, we use fmt.pix_mp (multi-planar pixel format).
	 * RGB3 = 24-bit RGB, one of the formats supported by ISI capture.
	 */
	struct v4l2_format fmt = { .type = buf_type };
	if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE) {
		fmt.fmt.pix_mp.width       = width;
		fmt.fmt.pix_mp.height      = height;
		fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_RGB24;
		fmt.fmt.pix_mp.num_planes  = 1;
	} else {
		fmt.fmt.pix.width       = width;
		fmt.fmt.pix.height      = height;
		fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_RGB24;
	}

	if (xioctl(fd, VIDIOC_S_FMT, &fmt) < 0) {
		perror("VIDIOC_S_FMT");
		close(fd);
		return 1;
	}

	if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE)
		printf("Format:  %dx%d, sizeimage=%d\n",
		       fmt.fmt.pix_mp.width, fmt.fmt.pix_mp.height,
		       fmt.fmt.pix_mp.plane_fmt[0].sizeimage);
	else
		printf("Format:  %dx%d, sizeimage=%d\n",
		       fmt.fmt.pix.width, fmt.fmt.pix.height,
		       fmt.fmt.pix.sizeimage);

	/*
	 * Step 4: Request kernel buffers (VIDIOC_REQBUFS).
	 *
	 * V4L2_MEMORY_MMAP = kernel allocates DMA-capable buffers,
	 * we mmap() them into our address space. Zero-copy: the ISI
	 * DMA engine writes directly to these buffers, no memcpy needed.
	 *
	 * Alternative: V4L2_MEMORY_USERPTR (we allocate), V4L2_MEMORY_DMABUF
	 * (share buffers with other devices like GPU — used by GStreamer).
	 */
	struct v4l2_requestbuffers req = {
		.count  = NUM_BUFFERS,
		.type   = buf_type,
		.memory = V4L2_MEMORY_MMAP,
	};
	if (xioctl(fd, VIDIOC_REQBUFS, &req) < 0) {
		perror("VIDIOC_REQBUFS");
		close(fd);
		return 1;
	}
	printf("Allocated %d buffers\n", req.count);

	/*
	 * Step 5: mmap each buffer into userspace.
	 *
	 * After this, buffers[i].start points to DMA buffer memory.
	 * When ISI captures a frame, data appears at this address
	 * without any copy — the DMA engine wrote directly there.
	 */
	for (i = 0; i < (int)req.count; i++) {
		struct v4l2_buffer buf = {
			.type   = buf_type,
			.memory = V4L2_MEMORY_MMAP,
			.index  = i,
		};
		struct v4l2_plane planes[1] = {};
		if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE) {
			buf.m.planes = planes;
			buf.length = 1;
		}

		if (xioctl(fd, VIDIOC_QUERYBUF, &buf) < 0) {
			perror("VIDIOC_QUERYBUF");
			close(fd);
			return 1;
		}

		size_t len;
		unsigned int offset;
		if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE) {
			len    = planes[0].length;
			offset = planes[0].m.mem_offset;
		} else {
			len    = buf.length;
			offset = buf.m.offset;
		}

		buffers[i].length = len;
		buffers[i].start = mmap(NULL, len, PROT_READ | PROT_WRITE,
					MAP_SHARED, fd, offset);
		if (buffers[i].start == MAP_FAILED) {
			perror("mmap");
			close(fd);
			return 1;
		}
	}

	/*
	 * Step 6: Queue all buffers and start streaming.
	 *
	 * QBUF hands an empty buffer to the driver.
	 * STREAMON tells the ISI to start DMA capture.
	 * The ISI fills buffers in round-robin order.
	 */
	for (i = 0; i < (int)req.count; i++) {
		struct v4l2_buffer buf = {
			.type   = buf_type,
			.memory = V4L2_MEMORY_MMAP,
			.index  = i,
		};
		struct v4l2_plane planes[1] = {};
		if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE) {
			buf.m.planes = planes;
			buf.length = 1;
		}

		if (xioctl(fd, VIDIOC_QBUF, &buf) < 0) {
			perror("VIDIOC_QBUF");
			close(fd);
			return 1;
		}
	}

	if (xioctl(fd, VIDIOC_STREAMON, &buf_type) < 0) {
		perror("VIDIOC_STREAMON");
		close(fd);
		return 1;
	}
	printf("Streaming started, capturing 5 frames...\n");

	/*
	 * Step 7: Dequeue frames (capture loop).
	 *
	 * DQBUF blocks until a frame is ready (ISI DMA complete).
	 * After processing, we QBUF to return the buffer for reuse.
	 * This is the producer-consumer pattern with the hardware.
	 */
	for (i = 0; i < 5; i++) {
		struct v4l2_buffer buf = {
			.type   = buf_type,
			.memory = V4L2_MEMORY_MMAP,
		};
		struct v4l2_plane planes[1] = {};
		if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE) {
			buf.m.planes = planes;
			buf.length = 1;
		}

		if (xioctl(fd, VIDIOC_DQBUF, &buf) < 0) {
			perror("VIDIOC_DQBUF");
			break;
		}

		size_t bytesused;
		if (buf_type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE)
			bytesused = planes[0].bytesused;
		else
			bytesused = buf.bytesused;

		printf("  Frame %d: buffer=%d, %zu bytes, seq=%d\n",
		       i, buf.index, bytesused, buf.sequence);

		/* Save the last frame as raw RGB */
		if (i == 4) {
			const char *outfile = "/tmp/frame.rgb";
			FILE *fp = fopen(outfile, "wb");
			if (fp) {
				fwrite(buffers[buf.index].start, 1,
				       bytesused, fp);
				fclose(fp);
				printf("Saved %s (%zu bytes, %dx%d RGB24)\n",
				       outfile, bytesused, width, height);
				printf("View: ffplay -f rawvideo -pix_fmt rgb24"
				       " -video_size %dx%d %s\n",
				       width, height, outfile);
			}
		}

		/* Return buffer to the driver for next capture */
		if (xioctl(fd, VIDIOC_QBUF, &buf) < 0) {
			perror("VIDIOC_QBUF (requeue)");
			break;
		}
	}

	/*
	 * Step 8: Stop streaming and cleanup.
	 */
	xioctl(fd, VIDIOC_STREAMOFF, &buf_type);
	for (i = 0; i < (int)req.count; i++)
		munmap(buffers[i].start, buffers[i].length);
	close(fd);
	printf("Done.\n");
	return 0;
}
