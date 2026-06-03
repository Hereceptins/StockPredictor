import SwiftUI

/// 涨跌停复盘 + 龙虎榜
struct BoardReviewView: View {
    @State private var selectedTab: ReviewTab = .limitUpDown
    @State private var selectedDate = Date()

    enum ReviewTab: String, CaseIterable {
        case limitUpDown = "涨跌停"
        case dragonTiger = "龙虎榜"
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $selectedTab) {
                    ForEach(ReviewTab.allCases, id: \.self) { t in
                        Text(t.rawValue).tag(t)
                    }
                }
                .pickerStyle(.segmented)
                .padding()

                DatePicker("日期", selection: $selectedDate, displayedComponents: .date)
                    .padding(.horizontal)
                    .padding(.bottom, 8)

                switch selectedTab {
                case .limitUpDown:
                    LimitUpDownView(date: selectedDate)
                case .dragonTiger:
                    DragonTigerView(date: selectedDate)
                }
            }
            .navigationTitle("复盘")
        }
    }
}

// MARK: - 涨跌停复盘

struct LimitUpDownView: View {
    let date: Date
    @State private var limitUpStocks: [LimitStock] = []
    @State private var limitDownStocks: [LimitStock] = []

    var body: some View {
        List {
            if !limitUpStocks.isEmpty {
                Section("涨停 (\(limitUpStocks.count))") {
                    ForEach(limitUpStocks) { stock in
                        LimitStockRow(stock: stock)
                    }
                }
            }

            if !limitDownStocks.isEmpty {
                Section("跌停 (\(limitDownStocks.count))") {
                    ForEach(limitDownStocks) { stock in
                        LimitStockRow(stock: stock)
                    }
                }
            }

            if limitUpStocks.isEmpty && limitDownStocks.isEmpty {
                ContentUnavailableView(
                    "非交易日或无数据",
                    systemImage: "chart.bar.xaxis"
                )
            }
        }
        .task {
            await loadData()
        }
    }

    private func loadData() async {
        // TODO: 调用后端API
    }
}

struct LimitStock: Identifiable {
    let id = UUID()
    let code: String
    let name: String
    let isLimitUp: Bool
    let consecutiveDays: Int
    let limitTime: String?
    let openLimit: Bool  // 一字板
}

struct LimitStockRow: View {
    let stock: LimitStock

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(stock.name)
                    .font(.subheadline)
                Text(stock.code)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            HStack(spacing: 4) {
                if stock.consecutiveDays > 1 {
                    Text("\(stock.consecutiveDays)连板")
                        .font(.caption.bold())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.orange.opacity(0.2))
                        .foregroundStyle(.orange)
                        .clipShape(Capsule())
                }

                if stock.openLimit {
                    Text("一字")
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.purple.opacity(0.2))
                        .foregroundStyle(.purple)
                        .clipShape(Capsule())
                }

                if let time = stock.limitTime {
                    Text(time)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - 龙虎榜

struct DragonTigerView: View {
    let date: Date
    @State private var entries: [DragonTigerEntry] = []

    var body: some View {
        List {
            if entries.isEmpty {
                ContentUnavailableView(
                    "非交易日或无数据",
                    systemImage: "list.clipboard"
                )
            } else {
                ForEach(entries) { entry in
                    DragonTigerRow(entry: entry)
                }
            }
        }
        .task { await loadData() }
    }

    private func loadData() async {
        // TODO: 调用后端API
    }
}

struct DragonTigerEntry: Identifiable {
    let id = UUID()
    let code: String
    let name: String
    let reason: String
    let buyAmount: Double
    let sellAmount: Double
    let netAmount: Double
    let seats: [SeatInfo]
}

struct SeatInfo: Identifiable {
    let id = UUID()
    let name: String
    let type: String  // buy / sell
    let amount: Double
}

struct DragonTigerRow: View {
    let entry: DragonTigerEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(entry.name)
                    .font(.headline)
                Text(entry.reason)
                    .font(.caption)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.1))
                    .foregroundStyle(.blue)
                    .clipShape(Capsule())

                Spacer()

                Text(String(format: "净%@%.0f万",
                            entry.netAmount >= 0 ? "买入" : "卖出",
                            abs(entry.netAmount) / 10000))
                .font(.subheadline.bold())
                .foregroundStyle(entry.netAmount >= 0 ? .red : .green)
            }

            // 席位信息
            if !entry.seats.isEmpty {
                HStack(spacing: 12) {
                    ForEach(entry.seats.prefix(3)) { seat in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(seat.name)
                                .font(.caption2)
                                .lineLimit(1)
                            Text(String(format: "%.0f万", seat.amount / 10000))
                                .font(.caption.bold())
                                .foregroundStyle(seat.type == "buy" ? .red : .green)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - 资讯页

struct SentimentView: View {
    @State private var newsItems: [NewsItem] = []
    @State private var marketSentiment: Double = 0.5  // 0=极度悲观, 1=极度乐观

    var body: some View {
        NavigationStack {
            List {
                // 市场情绪指标
                Section {
                    VStack(spacing: 8) {
                        HStack {
                            Text("市场情绪")
                                .font(.headline)
                            Spacer()
                            Text(marketSentiment > 0.6 ? "偏乐观" :
                                    marketSentiment > 0.4 ? "中性" : "偏悲观")
                                .foregroundStyle(marketSentiment > 0.6 ? .red :
                                                    marketSentiment > 0.4 ? .orange : .green)
                        }

                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(LinearGradient(
                                        gradient: Gradient(colors: [.green, .orange, .red]),
                                        startPoint: .leading, endPoint: .trailing))
                                    .frame(height: 8)
                                Circle()
                                    .fill(Color.white)
                                    .frame(width: 14, height: 14)
                                    .shadow(radius: 2)
                                    .offset(x: geo.size.width * marketSentiment - 7)
                            }
                        }
                        .frame(height: 14)
                    }
                    .padding(.vertical, 4)
                }

                // 新闻列表
                Section("财经资讯") {
                    ForEach(newsItems) { item in
                        NewsRow(item: item)
                    }
                }
            }
            .navigationTitle("资讯")
            .refreshable { await loadNews() }
            .task { await loadNews() }
        }
    }

    private func loadNews() async {
        // TODO: 从后端加载
    }
}

#Preview {
    BoardReviewView()
}
