# 05 — NPU & Edge AI with eIQ

## What's on the chip

The i.MX 8M Plus has a built-in NPU (Neural Processing Unit) — a **Verisilicon Vivante VIP8000** rated at **2.3 TOPS (INT8)**. Through NXP's eIQ software stack, you can run TensorFlow Lite, ONNX Runtime, and other inference frameworks directly on the board. That means real inference at the edge, no cloud round-trip needed.

## NPU specs at a glance

| Parameter | Value |
|-----------|-------|
| IP core | Verisilicon Vivante VIP8000 |
| Throughput | 2.3 TOPS (INT8) |
| Supported precision | INT8, INT16, FP16 |
| Memory | Shared DDR (via IOMMU) |
| Bus interface | AXI |

## eIQ software stack architecture

Here's how the layers fit together:

```
┌───────────────────────────────────┐
│          Application              │
│  (C++ / Python inference app)     │
├───────────────────────────────────┤
│  TensorFlow Lite  │  ONNX Runtime │
├───────────────────────────────────┤
│       VX Delegate / NNAPI         │
│  (offloads operators to NPU)      │
├───────────────────────────────────┤
│    OpenVX Driver (galcore)        │
│  (NPU kernel driver)             │
├───────────────────────────────────┤
│          NPU Hardware             │
└───────────────────────────────────┘
```

### Key components

| Component | Role |
|-----------|------|
| TensorFlow Lite | Lightweight inference engine — the primary framework in eIQ |
| VX Delegate | NXP's TFLite delegate that offloads supported ops to the NPU |
| ONNX Runtime | Alternative inference framework if you're coming from the ONNX ecosystem |
| OpenVX / galcore | Low-level NPU kernel driver — **closed-source blob** from Verisilicon |

## Enabling eIQ in your Yocto image

The quickest way is to pull in the whole ML package group:

```bash
IMAGE_INSTALL:append = " packagegroup-imx-ml"
```

If you want finer control over what gets installed:

```bash
IMAGE_INSTALL:append = " \
    tensorflow-lite \
    tensorflow-lite-vx-delegate \
    python3-tflite-runtime \
    onnxruntime \
"
```

I covered the Yocto build setup in [03-yocto-bsp.md](03-yocto-bsp.md) — the `packagegroup-imx-ml` line was already mentioned there in the `local.conf` customization section.

## Running inference with TFLite + VX Delegate

The VX Delegate is what moves computation from the Cortex-A53 to the NPU. Without it, TFLite still works — it just runs everything on the CPU.

### C++ example

```cpp
#include "tensorflow/lite/interpreter.h"
#include "tensorflow/lite/kernels/register.h"
#include "tensorflow/lite/model.h"
#include "tensorflow/lite/delegates/external/external_delegate.h"

int main() {
    // Load the quantized model
    auto model = tflite::FlatBufferModel::BuildFromFile("model_quant.tflite");
    tflite::ops::builtin::BuiltinOpResolver resolver;
    std::unique_ptr<tflite::Interpreter> interpreter;
    tflite::InterpreterBuilder(*model, resolver)(&interpreter);

    // Attach the VX Delegate — this is where NPU offload happens
    auto ext_delegate_option = TfLiteExternalDelegateOptionsDefault(
        "/usr/lib/libvx_delegate.so");
    auto ext_delegate = TfLiteExternalDelegateCreate(&ext_delegate_option);
    interpreter->ModifyGraphWithDelegate(ext_delegate);
    interpreter->AllocateTensors();

    // Feed input data
    float* input = interpreter->typed_input_tensor<float>(0);
    // ... fill with sensor data ...

    // Run inference
    interpreter->Invoke();

    // Read output
    float* output = interpreter->typed_output_tensor<float>(0);
    // ... process results ...

    TfLiteExternalDelegateDelete(ext_delegate);
    return 0;
}
```

### Python example

```python
import numpy as np
import tflite_runtime.interpreter as tflite

# Load delegate for NPU offload
delegate = tflite.load_delegate('/usr/lib/libvx_delegate.so')
interpreter = tflite.Interpreter(
    model_path='model_quant.tflite',
    experimental_delegates=[delegate]
)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Example: 6 sensor readings as input
input_data = np.array(
    [[temp, humidity, pressure, accel_x, accel_y, accel_z]],
    dtype=np.float32
)
interpreter.set_tensor(input_details[0]['index'], input_data)
interpreter.invoke()

output = interpreter.get_tensor(output_details[0]['index'])
is_anomaly = output[0][0] > 0.5
```

## Model quantization workflow

The NPU runs best with INT8 models. The typical workflow is: train in float on your PC, quantize to INT8, then deploy the `.tflite` file to the board.

### Step 1 — Train on PC (TensorFlow / Keras)

```python
model = tf.keras.Sequential([
    tf.keras.layers.Dense(32, activation='relu', input_shape=(6,)),
    tf.keras.layers.Dense(16, activation='relu'),
    tf.keras.layers.Dense(1, activation='sigmoid')
])
model.compile(optimizer='adam', loss='binary_crossentropy')
model.fit(train_data, train_labels, epochs=50)
model.save('sensor_anomaly_model')
```

### Step 2 — Post-training quantization (INT8)

```python
converter = tf.lite.TFLiteConverter.from_saved_model('sensor_anomaly_model')
converter.optimizations = [tf.lite.Optimize.DEFAULT]

# Calibration dataset — the converter uses this to determine quantization ranges
def representative_dataset():
    for data in calibration_data:
        yield [np.array(data, dtype=np.float32).reshape(1, 6)]

converter.representative_dataset = representative_dataset
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8

tflite_model = converter.convert()
with open('model_quant.tflite', 'wb') as f:
    f.write(tflite_model)
```

### Step 3 — Deploy to the EVK

```bash
scp model_quant.tflite root@<EVK_IP>:/opt/models/
python3 inference.py
```

Nothing fancy — just `scp` and run. The VX Delegate picks up the INT8 model and routes it through the NPU automatically.

## Benchmarking

NXP ships a `benchmark_model` binary in the TFLite package. Use it to get real latency numbers:

```bash
/usr/bin/tensorflow-lite-2.*/tools/benchmark_model \
    --graph=model_quant.tflite \
    --external_delegate_path=/usr/lib/libvx_delegate.so \
    --num_runs=100 --warmup_runs=5
```

### Ballpark performance numbers

| Model | CPU (A53) | NPU (VX Delegate) | Speedup |
|-------|-----------|-------------------|---------|
| MobileNet V2 (INT8) | ~200 ms | ~10 ms | ~20x |
| Simple FC (6 -> 32 -> 16 -> 1) | ~0.1 ms | ~0.05 ms | ~2x |

The takeaway: **small models don't benefit much from the NPU**. The delegate launch overhead eats into the compute time. The NPU really shines on larger models — convolutions, attention blocks, anything with enough arithmetic intensity to justify the dispatch cost.

## Example project: sensor anomaly detection

This is a practical use case that ties together the heterogeneous architecture (M7 core + A53 Linux + NPU).

### Data flow

```
MPU6050 (M7 / FreeRTOS)
    ↓ RPMsg
A53 Linux
    ↓ + BME280 data
Data fusion
    ↓
TFLite inference (NPU)
    ↓
Anomaly detection result
    ↓
Web UI / OLED display
```

The M7 core handles the fast sensor sampling over I2C, ships data to the A53 side via RPMsg, where it gets fused with slower environmental sensor readings and fed into the neural network.

### Demo scenarios

- **Predictive maintenance**: vibration pattern goes abnormal -> equipment fault warning
- **Environmental monitoring**: temperature/humidity spike -> alert
- **Fall detection**: sudden acceleration change -> trigger notification

## Gotchas and practical notes

- **galcore is closed-source.** When you hit weird NPU behavior, there's no source to read. Check the [NXP Community Forum](https://community.nxp.com/) first — someone has probably hit the same issue.
- **Not all TFLite ops are NPU-accelerated.** Unsupported ops silently fall back to CPU execution. You won't get an error, just worse performance. Run `benchmark_model` with and without the delegate to see what's actually being offloaded.
- **INT8 quantization can hurt accuracy.** Always compare your quantized model's output against the float original on a test set before deploying. Small models with few parameters are especially sensitive to quantization noise.
