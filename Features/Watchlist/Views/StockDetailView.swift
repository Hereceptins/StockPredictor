import SwiftUI
import SwiftData

/// 个股详情页 —— K线 + 预测 + 资讯 三Tab
struct StockDetailView: View {
    let stock: StockItem
    @State private var selectedTab: DetailTab = .chart

    enum DetailTab: String, CaseIterable {
        case chart = "K线"
        case prediction = "预测"
        case sentiment = "资讯"
        case info = "概况"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // 头部：名称+价格信息
                StockHeaderView(stock: stock)
                    .padding(.horizontal)
                    .padding(.vertical, 12)

                Divider()

                // Tab切换
                Picker("", selection: $selectedTab) {
                    ForEach(DetailTab.allCases, id: \.self) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding()

                // 内容区
                switch selectedTab {
                case .chart:
                    KLineChartView(stockCode: stock.code)

                case .prediction:
                    StockPredictionView(stock: stock)

                case .sentiment:
                    StockSentimentView(stock: stock)

                case .info:
                    StockInfoView(stock: stock)
                }
            }
        }
        .navigationTitle(stock.name)
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - 头部视图

struct StockHeaderView: View {
    let stock: StockItem

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(stock.name)
                        .font(.title2.bold())
                    Text(stock.marketShort)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.orange.opacity(0.15))
                        .foregroundStyle(.orange)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
                Text(stock.symbol)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                if let industry = stock.industry {
                    Text(industry)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 4) {
                if let price = stock.latestPrice {
                    Text(String(format: "%.2f", price))
                        .font(.title.bold().monospacedDigit())
                }
                if let change = stock.latestChange {
                    HStack(spacing: 2) {
                        Text(String(format: "%+.2f", change))
                        Text(String(format: "%.2f%%", change / ((stock.latestPrice ?? 1) - change) * 100))
                            .font(.caption)
                    }
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(change >= 0 ? .red : .green)
                }
            }
        }
    }
}

// MARK: - 预测Tab

struct StockPredictionView: View {
    let stock: StockItem

    var body: some View {
        VStack(spacing: 16) {
            PredictionCardView(stock: stock)

            // 历史预测准确率
            HistoryAccuracyCard(stock: stock)
        }
        .padding()
    }
}

struct HistoryAccuracyCard: View {
    let stock: StockItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("预测历史")
                .font(.headline)

            HStack(spacing: 20) {
                StatItem(label: "近30日准确率", value: "--%")
                StatItem(label: "近90日准确率", value: "--%")
                StatItem(label: "总预测次数", value: "--")
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.05), radius: 4)
    }
}

struct StatItem: View {
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title3.bold())
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - 资讯Tab

struct StockSentimentView: View {
    let stock: StockItem
    @State private var news: [NewsItem] = []

    var body: some View {
        VStack {
            if news.isEmpty {
                ContentUnavailableView(
                    "暂无相关资讯",
                    systemImage: "newspaper",
                    description: Text("加载中...")
                )
            } else {
                ForEach(news) { item in
                    NewsRow(item: item)
                }
            }
        }
        .padding()
    }
}

struct NewsItem: Identifiable {
    let id = UUID()
    let title: String
    let source: String
    let sentiment: String  // positive/negative/neutral
    let time: String
}

struct NewsRow: View {
    let item: NewsItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(item.sentiment == "positive" ? Color.red :
                        item.sentiment == "negative" ? Color.green : Color.gray)
                .frame(width: 8, height: 8)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.subheadline)
                    .lineLimit(2)
                HStack {
                    Text(item.source)
                    Text("·")
                    Text(item.time)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - 概况Tab

struct StockInfoView: View {
    let stock: StockItem

    var body: some View {
        VStack(spacing: 16) {
            InfoRow(label: "股票代码", value: stock.code)
            InfoRow(label: "上市市场", value: stock.market)
            InfoRow(label: "所属行业", value: stock.industry ?? "未知")
            if let date = stock.listDate {
                InfoRow(label: "上市日期", value: date.formatted(date: .long, time: .omitted))
            }
            if let cap = stock.marketCap {
                InfoRow(label: "总市值", value: String(format: "%.0f亿", cap))
            }
            if let pe = stock.pe {
                InfoRow(label: "市盈率(PE)", value: String(format: "%.2f", pe))
            }
        }
        .padding()
    }
}

struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
        }
        .font(.subheadline)
    }
}

#Preview {
    NavigationStack {
        StockDetailView(stock: StockItem(code: "000001.SZ", name: "平安银行", market: "SZ", industry: "银行"))
    }
}
