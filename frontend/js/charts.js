/**
 * OpenClaw Enterprise - 前端图表组件库
 * 基于 Chart.js 的封装
 */

// 全局图表配置
const CHART_CONFIG = {
  colors: {
    primary: '#6366f1',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#0ea5e9',
    dark: '#1e293b',
    border: '#334155'
  },
  fonts: {
    family: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    size: 12
  }
};

/**
 * 创建风险分布饼图
 */
function createRiskDistributionChart(ctx, data) {
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['低风险', '中风险', '高风险'],
      datasets: [{
        data: data,
        backgroundColor: [
          CHART_CONFIG.colors.success,
          CHART_CONFIG.colors.warning,
          CHART_CONFIG.colors.danger
        ],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: CHART_CONFIG.colors.info,
            font: { size: 11 }
          }
        }
      },
      cutout: '60%'
    }
  });
}

/**
 * 创建告警趋势折线图
 */
function createAlertTrendChart(ctx, labels, data) {
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '告警数量',
        data: data,
        borderColor: CHART_CONFIG.colors.danger,
        backgroundColor: 'rgba(239, 68, 68, 0.1)',
        fill: true,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: CHART_CONFIG.colors.border },
          ticks: { color: CHART_CONFIG.colors.info }
        },
        x: {
          grid: { display: false },
          ticks: { color: CHART_CONFIG.colors.info }
        }
      }
    }
  });
}

/**
 * 创建操作类型分布图
 */
function createOperationTypeChart(ctx, data) {
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['文件操作', '命令执行', 'API 调用', '消息发送'],
      datasets: [{
        label: '操作次数',
        data: data,
        backgroundColor: [
          CHART_CONFIG.colors.primary,
          CHART_CONFIG.colors.warning,
          CHART_CONFIG.colors.danger,
          CHART_CONFIG.colors.info
        ],
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: CHART_CONFIG.colors.border },
          ticks: { color: CHART_CONFIG.colors.info }
        },
        x: {
          grid: { display: false },
          ticks: { color: CHART_CONFIG.colors.info }
        }
      }
    }
  });
}

/**
 * 创建设备状态仪表盘
 */
function createDeviceStatusGauge(ctx, value, max = 100) {
  return new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['已使用', '剩余'],
      datasets: [{
        data: [value, max - value],
        backgroundColor: [
          value > 80 ? CHART_CONFIG.colors.danger : 
          value > 60 ? CHART_CONFIG.colors.warning : 
          CHART_CONFIG.colors.success,
          CHART_CONFIG.colors.dark
        ],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      circumference: 180,
      rotation: 270,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      },
      cutout: '80%'
    }
  });
}

/**
 * 创建流量分析堆叠图
 */
function createTrafficStackedChart(ctx, labels, normalData, openclawData, llmData) {
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: '正常流量',
          data: normalData,
          backgroundColor: CHART_CONFIG.colors.success,
          stack: 'Stack 0'
        },
        {
          label: 'OpenClaw',
          data: openclawData,
          backgroundColor: CHART_CONFIG.colors.warning,
          stack: 'Stack 0'
        },
        {
          label: 'LLM 调用',
          data: llmData,
          backgroundColor: CHART_CONFIG.colors.danger,
          stack: 'Stack 0'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          ticks: { color: CHART_CONFIG.colors.info }
        },
        y: {
          stacked: true,
          beginAtZero: true,
          grid: { color: CHART_CONFIG.colors.border },
          ticks: { color: CHART_CONFIG.colors.info }
        }
      }
    }
  });
}

/**
 * 更新图表数据
 */
function updateChartData(chart, newData, newLabels = null) {
  if (newLabels) {
    chart.data.labels = newLabels;
  }
  chart.data.datasets[0].data = newData;
  chart.update('none');
}

/**
 * 销毁图表
 */
function destroyChart(chart) {
  if (chart) {
    chart.destroy();
  }
}

// 导出函数
window.OpenClawCharts = {
  createRiskDistributionChart,
  createAlertTrendChart,
  createOperationTypeChart,
  createDeviceStatusGauge,
  createTrafficStackedChart,
  updateChartData,
  destroyChart,
  config: CHART_CONFIG
};
