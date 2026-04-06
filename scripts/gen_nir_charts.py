#!/usr/bin/env python3
"""
Generate NIR sensor experiment charts from measured data.
Data source: Weekly Meeting 260408 experimental records.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

# ── Chinese font setup ──
# Try Microsoft YaHei (Windows), fall back to SimHei
for fname in ['Microsoft YaHei', 'SimHei', 'PingFang SC', 'WenQuanYi Micro Hei']:
    if any(fname in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams['font.sans-serif'] = [fname]
        break
plt.rcParams['axes.unicode_minus'] = False

# ── Dark theme ──
plt.rcParams.update({
    'figure.facecolor': '#0a0a0f',
    'axes.facecolor': '#12121a',
    'axes.edgecolor': '#333',
    'axes.labelcolor': '#ccc',
    'text.color': '#ddd',
    'xtick.color': '#aaa',
    'ytick.color': '#aaa',
    'grid.color': '#222',
    'grid.linestyle': '--',
    'grid.alpha': 0.5,
    'font.size': 11,
    'axes.titlesize': 14,
    'legend.facecolor': '#1a1a24',
    'legend.edgecolor': '#333',
})

CYAN = '#00d4ff'
GREEN = '#33ff88'
YELLOW = '#ffcc33'
RED = '#ff4444'
ORANGE = '#ff8833'
PURPLE = '#aa66ff'
WHITE = '#ffffff'

OUT = 'c:/Users/corni/OneDrive - Nanyang Technological University/ntu_rf/M266_EmbeddedLinux/docs/'


# ════════════════════════════════════════════
# Chart 1: Calibrated Cold Stimulus — TOI_cal over time
# ════════════════════════════════════════════
def chart_cold_stimulus_calibrated():
    time_s = [0, 15, 30, 45, 60]
    toi_cal = [-0.118, -0.128, -0.145, -0.167, -0.173]
    temp = [25, 26, 27, 27, 29]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()

    l1 = ax1.plot(time_s, toi_cal, 'o-', color=GREEN, linewidth=2.5,
                  markersize=8, label='TOI_cal', zorder=5)
    ax1.axhline(-0.210, color=CYAN, linestyle='--', alpha=0.6, linewidth=1.5,
                label='暖手基线 (-0.210)')
    ax1.axhline(-0.12, color=RED, linestyle=':', alpha=0.5, linewidth=1.5,
                label='危险阈值 (-0.12)')
    ax1.axhline(-0.15, color=YELLOW, linestyle=':', alpha=0.5, linewidth=1.5,
                label='警告阈值 (-0.15)')

    ax1.axhspan(-0.08, -0.12, alpha=0.08, color=RED)
    ax1.axhspan(-0.12, -0.15, alpha=0.08, color=YELLOW)
    ax1.axhspan(-0.15, -0.25, alpha=0.05, color=GREEN)

    l2 = ax2.plot(time_s, temp, 's--', color=ORANGE, linewidth=1.5,
                  markersize=6, alpha=0.7, label='皮肤温度 (°C)')

    ax1.set_xlabel('冷刺激移除后时间 (秒)')
    ax1.set_ylabel('TOI_cal (白纸校准后)')
    ax2.set_ylabel('皮肤温度 (°C)', color=ORANGE)
    ax1.set_title('校准后冷刺激测试 — TOI_cal 恢复曲线 (起始 25°C)')
    ax1.set_ylim(-0.24, -0.08)
    ax2.set_ylim(23, 31)
    ax1.grid(True)

    lines = l1 + l2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right', fontsize=9)

    ax1.annotate('接近冻伤\n(手已快受不了)',
                 xy=(0, -0.118), xytext=(15, -0.10),
                 arrowprops=dict(arrowstyle='->', color=RED, lw=1.5),
                 fontsize=9, color=RED, ha='center')
    ax1.annotate('反应性充血开始',
                 xy=(45, -0.167), xytext=(50, -0.20),
                 arrowprops=dict(arrowstyle='->', color=CYAN, lw=1.5),
                 fontsize=9, color=CYAN, ha='center')

    plt.tight_layout()
    plt.savefig(OUT + 'nir_cold_calibrated.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] nir_cold_calibrated.png')


# ════════════════════════════════════════════
# Chart 2: Three correction methods comparison
# ════════════════════════════════════════════
def chart_three_methods():
    phases = ['冷却期\n#4-#8', '缓慢下降\n#9-#18', '复温期\n#19-#30', '暖手\n基线']
    toi_raw = [-0.733, -0.740, -0.746, -0.766]
    toi_cal = [-0.14, -0.16, -0.17, -0.21]
    sto2 = [0.43, 0.40, 0.24, 0.38]

    x = np.arange(len(phases))
    w = 0.25

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 5))

    bars1 = ax1.bar(x, toi_raw, w, color=RED, alpha=0.8)
    ax1.set_title('原始 TOI\n(无校正)', color=RED)
    ax1.set_ylabel('TOI')
    ax1.set_xticks(x)
    ax1.set_xticklabels(phases, fontsize=8)
    ax1.set_ylim(-0.80, -0.70)
    ax1.grid(True, axis='y')
    ax1.bar_label(bars1, fmt='%.3f', fontsize=8, color='#aaa')

    bars2 = ax2.bar(x, toi_cal, w, color=YELLOW, alpha=0.8)
    ax2.set_title('白纸校准 TOI\n(去除 LED 偏差)', color=YELLOW)
    ax2.set_ylabel('TOI_cal')
    ax2.set_xticks(x)
    ax2.set_xticklabels(phases, fontsize=8)
    ax2.set_ylim(-0.25, -0.05)
    ax2.grid(True, axis='y')
    ax2.bar_label(bars2, fmt='%.2f', fontsize=8, color='#aaa')

    colors3 = [RED if v > 0.43 else YELLOW if v > 0.40 else GREEN for v in sto2]
    bars3 = ax3.bar(x, sto2, w, color=colors3, alpha=0.8)
    ax3.set_title('DPF 校正 StO2\n(指尖, 生理意义)', color=GREEN)
    ax3.set_ylabel('StO2')
    ax3.set_xticks(x)
    ax3.set_xticklabels(phases, fontsize=8)
    ax3.set_ylim(0, 0.55)
    ax3.axhline(0.43, color=RED, linestyle=':', alpha=0.5, label='危险')
    ax3.axhline(0.40, color=YELLOW, linestyle=':', alpha=0.5, label='警告')
    ax3.grid(True, axis='y')
    ax3.bar_label(bars3, fmt='%.2f', fontsize=8, color='#aaa')
    ax3.legend(fontsize=8)

    fig.suptitle('三种校正方法对比 — 同一组冷刺激数据', fontsize=15, color=WHITE, y=1.02)
    plt.tight_layout()
    plt.savefig(OUT + 'nir_three_methods.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] nir_three_methods.png')


# ════════════════════════════════════════════
# Chart 3: Five-session reproducibility
# ════════════════════════════════════════════
def chart_reproducibility():
    sessions = ['暖手\n基线', '冷测 #1\n手动', '冷测 #2\n校准', '冷测 #3\n倒计时', '冷测 #4\n轻度']
    endpoints = [-0.21, -0.17, -0.20, -0.17, -0.17]
    colors = [CYAN, GREEN, GREEN, GREEN, GREEN]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(range(len(sessions)), endpoints, color=colors, alpha=0.85, width=0.6)

    ax.axhspan(-0.21, -0.17, alpha=0.12, color=CYAN,
               label='收敛区间 (-0.17 ~ -0.21)')
    ax.axhline(-0.21, color=CYAN, linestyle='--', alpha=0.6, linewidth=1)
    ax.axhline(-0.17, color=CYAN, linestyle='--', alpha=0.6, linewidth=1)

    ax.set_xticks(range(len(sessions)))
    ax.set_xticklabels(sessions, fontsize=9)
    ax.set_ylabel('复温终点 TOI_cal')
    ax.set_title('五次实验可重复性 — 终点全部收敛到 -0.17 ~ -0.21')
    ax.set_ylim(-0.25, -0.10)
    ax.grid(True, axis='y')
    ax.legend(fontsize=9)
    ax.bar_label(bars, fmt='%.2f', fontsize=10, color=WHITE, padding=3)

    plt.tight_layout()
    plt.savefig(OUT + 'nir_reproducibility.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] nir_reproducibility.png')


# ════════════════════════════════════════════
# Chart 4: DPF site sensitivity comparison
# ════════════════════════════════════════════
def chart_dpf_site_comparison():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    sites = ['前臂\n(DPF比值 1.11)', '指尖\n(DPF比值 1.20)']
    cold_sto2 = [0.39, 0.43]
    warm_sto2 = [0.36, 0.24]
    baseline_sto2 = [0.37, 0.38]

    x = np.arange(2)
    w = 0.2
    ax1.bar(x - w, cold_sto2, w, color=CYAN, alpha=0.8, label='冷 (血管收缩)')
    ax1.bar(x, baseline_sto2, w, color=GREEN, alpha=0.8, label='暖手基线')
    ax1.bar(x + w, warm_sto2, w, color=ORANGE, alpha=0.8, label='反应性充血谷值')

    ax1.set_xticks(x)
    ax1.set_xticklabels(sites, fontsize=10)
    ax1.set_ylabel('StO2')
    ax1.set_title('不同测量部位的 StO2 动态范围')
    ax1.set_ylim(0, 0.55)
    ax1.legend(fontsize=8)
    ax1.grid(True, axis='y')

    ax1.annotate('', xy=(0, 0.36), xytext=(0, 0.39),
                 arrowprops=dict(arrowstyle='<->', color=RED, lw=2))
    ax1.text(0.15, 0.375, '0.03\n(被压缩!)', fontsize=9, color=RED, ha='left')

    ax1.annotate('', xy=(1, 0.24), xytext=(1, 0.43),
                 arrowprops=dict(arrowstyle='<->', color=GREEN, lw=2))
    ax1.text(1.15, 0.33, '0.19\n(范围宽)', fontsize=9, color=GREEN, ha='left')

    body_sites = ['额头', '太阳穴', '新生儿\n头部', '小腿', '大腿',
                  '前臂', '指尖', '手掌']
    dpf_ratios = [1.20, 1.22, 1.19, 1.16, 1.16, 1.16, 1.20, 1.15]
    colors = [PURPLE if r >= 1.19 else CYAN for r in dpf_ratios]
    colors[6] = GREEN

    bars = ax2.barh(range(len(body_sites)), dpf_ratios, color=colors, alpha=0.8)
    ax2.set_yticks(range(len(body_sites)))
    ax2.set_yticklabels(body_sites, fontsize=9)
    ax2.set_xlabel('DPF 比值 (680nm / 860nm)')
    ax2.set_title('人体各部位 DPF 比值\n(越高 = 灵敏度越好)')
    ax2.set_xlim(1.10, 1.28)
    ax2.axvline(1.16, color='#444', linestyle=':', alpha=0.5)
    ax2.grid(True, axis='x')
    ax2.bar_label(bars, fmt='%.2f', fontsize=9, color=WHITE, padding=3)

    plt.tight_layout()
    plt.savefig(OUT + 'nir_dpf_site_comparison.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] nir_dpf_site_comparison.png')


# ════════════════════════════════════════════
# Chart 5: Frostbite warning threshold visualization
# ════════════════════════════════════════════
def chart_frostbite_threshold():
    samples = list(range(5, 30))
    toi_cal_data = (
        [-0.12]*3 + [-0.12, -0.13, -0.13] +
        [-0.14, -0.15, -0.155, -0.16, -0.165, -0.17] +
        [-0.17, -0.175, -0.18, -0.18, -0.185, -0.19, -0.19, -0.19] +
        [-0.19, -0.195, -0.195, -0.20, -0.20]
    )

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.axhspan(-0.08, -0.12, alpha=0.15, color=RED,
               label='危险区 (> -0.12)')
    ax.axhspan(-0.12, -0.15, alpha=0.12, color=YELLOW,
               label='警告区 (-0.15 ~ -0.12)')
    ax.axhspan(-0.15, -0.25, alpha=0.08, color=GREEN,
               label='安全区 (< -0.15)')

    ax.axhline(-0.12, color=RED, linestyle='-', alpha=0.7, linewidth=2)
    ax.axhline(-0.15, color=YELLOW, linestyle='-', alpha=0.7, linewidth=2)
    ax.axhline(-0.210, color=CYAN, linestyle='--', alpha=0.5, linewidth=1.5)

    ax.plot(samples, toi_cal_data, '-', color=WHITE, linewidth=1.5, alpha=0.6)
    for i, (s, v) in enumerate(zip(samples, toi_cal_data)):
        if v > -0.12:
            c = RED
        elif v > -0.15:
            c = YELLOW
        else:
            c = GREEN
        ax.plot(s, v, 'o', color=c, markersize=7, zorder=5)

    ax.text(7, -0.105, '危险\n立即停止冷敷!', fontsize=11, color=RED,
            ha='center', weight='bold')
    ax.text(13, -0.135, '警告', fontsize=10, color=YELLOW,
            ha='center', weight='bold')
    ax.text(22, -0.22, '安全', fontsize=10, color=GREEN,
            ha='center', weight='bold')
    ax.text(28, -0.215, '基线 -0.210', fontsize=8, color=CYAN, ha='right')

    ax.annotate('严重血管收缩', xy=(6, -0.12), xytext=(3, -0.09),
                arrowprops=dict(arrowstyle='->', color=WHITE, lw=1),
                fontsize=8, color='#aaa', ha='center')
    ax.annotate('反应性充血', xy=(20, -0.19), xytext=(24, -0.16),
                arrowprops=dict(arrowstyle='->', color=WHITE, lw=1),
                fontsize=8, color='#aaa', ha='center')

    ax.set_xlabel('采样点 (每2秒一个)')
    ax.set_ylabel('TOI_cal')
    ax.set_title('冻伤预警系统 — 三级阈值可视化')
    ax.set_ylim(-0.24, -0.08)
    ax.set_xlim(4, 30)
    ax.legend(loc='lower right', fontsize=9)
    ax.grid(True)

    plt.tight_layout()
    plt.savefig(OUT + 'nir_frostbite_threshold.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] nir_frostbite_threshold.png')


if __name__ == '__main__':
    chart_cold_stimulus_calibrated()
    chart_three_methods()
    chart_reproducibility()
    chart_dpf_site_comparison()
    chart_frostbite_threshold()
    print('\nAll charts generated in docs/')
