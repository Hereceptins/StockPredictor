import SwiftUI
import WebKit

/// K线图表 —— WKWebView 桥接 TradingView Lightweight Charts
struct KLineChartView: View {
    let stockCode: String
    @State private var selectedPeriod: Period = .daily
    @State private var selectedIndicator: Indicator = .macd

    enum Period: String, CaseIterable {
        case daily = "日K"
        case weekly = "周K"
        case monthly = "月K"
    }

    enum Indicator: String, CaseIterable {
        case macd = "MACD"
        case kdj = "KDJ"
        case rsi = "RSI"
        case boll = "BOLL"
        case none = "无"
    }

    var body: some View {
        VStack(spacing: 0) {
            // 周期选择器
            Picker("周期", selection: $selectedPeriod) {
                ForEach(Period.allCases, id: \.self) { p in
                    Text(p.rawValue).tag(p)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.vertical, 8)

            // K线图
            KLineWebView(stockCode: stockCode,
                         period: selectedPeriod,
                         indicator: selectedIndicator)
                .frame(height: 320)

            // 指标切换
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Indicator.allCases, id: \.self) { ind in
                        Button {
                            selectedIndicator = ind
                        } label: {
                            Text(ind.rawValue)
                                .font(.caption.bold())
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(selectedIndicator == ind ? Color.orange : Color(.systemGray6))
                                .foregroundStyle(selectedIndicator == ind ? .white : .primary)
                                .clipShape(Capsule())
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
        }
    }
}

/// WKWebView 封装 — TradingView Lightweight Charts
struct KLineWebView: UIViewRepresentable {
    let stockCode: String
    let period: KLineChartView.Period
    let indicator: KLineChartView.Indicator

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        loadChart(in: webView)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        // 指标或周期变化时更新
        let js = """
        updateIndicator('\(indicator.rawValue)');
        """
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    private func loadChart(in webView: WKWebView) {
        let html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <script src="https://unpkg.com/lightweight-charts@4.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: transparent; }
        #chart { width: 100%; height: 300px; }
        </style>
        </head>
        <body>
        <div id="chart"></div>
        <script>
        const chart = LightweightCharts.createChart(document.getElementById('chart'), {
            layout: {
                background: { type: 'solid', color: 'transparent' },
                textColor: '#333',
            },
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: '#ddd' },
            timeScale: { borderColor: '#ddd', timeVisible: true },
        });

        const candleSeries = chart.addCandlestickSeries({
            upColor: '#e74c3c',
            downColor: '#2ecc71',
            borderUpColor: '#e74c3c',
            borderDownColor: '#2ecc71',
            wickUpColor: '#e74c3c',
            wickDownColor: '#2ecc71',
        });

        // 初始化加载数据（示例数据，实际通过JS桥接注入）
        function loadData(data) {
            candleSeries.setData(data);
            chart.timeScale().fitContent();
        }

        // 加载示例数据
        const sampleData = [];
        const start = new Date('2024-01-01');
        let price = 15 + Math.random() * 5;
        for (let i = 0; i < 120; i++) {
            const d = new Date(start);
            d.setDate(d.getDate() + i);
            if (d.getDay() === 0 || d.getDay() === 6) continue;
            const open = price;
            const close = open + (Math.random() - 0.48) * 0.5;
            const high = Math.max(open, close) + Math.random() * 0.3;
            const low = Math.min(open, close) - Math.random() * 0.3;
            sampleData.push({
                time: d.toISOString().split('T')[0],
                open: +open.toFixed(2),
                high: +high.toFixed(2),
                low: +low.toFixed(2),
                close: +close.toFixed(2),
            });
            price = close;
        }
        candleSeries.setData(sampleData);
        chart.timeScale().fitContent();

        function updateIndicator(type) {
            // TODO: 根据type切换MACD/KDJ/RSI/BOLL子图指标
        }
        </script>
        </body>
        </html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }
}

#Preview {
    KLineChartView(stockCode: "000001.SZ")
}
