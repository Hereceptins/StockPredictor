import SwiftUI

/// 精选池排名视图 —— 带排名的AI推荐列表
struct RankedPoolView: View {
    @StateObject private var vm = RankedPoolViewModel()
    @State private var selectedFilter: PoolFilter = .all

    enum PoolFilter: String, CaseIterable {
        case all = "全部"
        case moneyFlow = "资金流入"
        case policy = "政策催化"
        case technical = "技术突破"
        case sentiment = "情绪反转"
    }

    var body: some View {
        VStack(spacing: 0) {
            // 筛选条
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(PoolFilter.allCases, id: \.self) { filter in
                        Button {
                            selectedFilter = filter
                        } label: {
                            Text(filter.rawValue)
                                .font(.subheadline.bold())
                                .padding(.horizontal, 14)
                                .padding(.vertical, 7)
                                .background(selectedFilter == filter ? Color.orange : Color(.systemGray6))
                                .foregroundStyle(selectedFilter == filter ? .white : .secondary)
                                .clipShape(Capsule())
                        }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.vertical, 10)

            // 排名列表
            if vm.isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("AI正在分析全市场数据...")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .frame(maxHeight: .infinity)
            } else {
                List {
                    ForEach(Array(vm.rankedStocks.enumerated()), id: \.element.id) { index, ranked in
                        RankedStockCard(
                            rank: index + 1,
                            stock: ranked,
                            isNew: vm.newAdditions.contains(ranked.id)
                        )
                        .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                        .listRowSeparator(.hidden)
                    }
                }
                .listStyle(.plain)
                .refreshable { await vm.refresh() }
            }
        }
        .task { await vm.loadRankedPool() }
    }
}

// MARK: - 排名卡片（核心组件）

struct RankedStockCard: View {
    let rank: Int
    let stock: RankedStock
    let isNew: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                // 排名徽章
                RankBadge(rank: rank, isNew: isNew)
                    .frame(width: 36)

                // 股票信息
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(stock.name)
                            .font(.headline)
                        Text(stock.symbol)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if stock.market == "科创" {
                            MarketTag("科创", color: .purple)
                        } else if stock.market == "创业" {
                            MarketTag("创业", color: .blue)
                        }
                    }

                    HStack(spacing: 8) {
                        Text(stock.industry)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if let price = stock.latestPrice {
                            Text(String(format: "¥%.2f", price))
                                .font(.caption.monospacedDigit())
                        }
                        if let change = stock.latestChange {
                            Text(String(format: "%+.2f%%", change))
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(change >= 0 ? .red : .green)
                        }
                    }
                }

                Spacer()

                // 右侧：方向 + 得分
                VStack(alignment: .trailing, spacing: 6) {
                    // 方向指示
                    HStack(spacing: 4) {
                        Image(systemName: stock.direction == "up" ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                            .font(.title3)
                        Text(stock.direction == "up" ? "看涨" : "看淡")
                            .font(.subheadline.bold())
                    }
                    .foregroundStyle(stock.direction == "up" ? .red : .green)

                    // 综合得分
                    Text("\(Int(stock.overallScore))分")
                        .font(.title2.bold().monospacedDigit())
                        .foregroundStyle(scoreColor(stock.overallScore))
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            // 底部：信号标签 + 置信度
            HStack(spacing: 6) {
                ForEach(stock.signalTags, id: \.self) { tag in
                    SignalTagView(tag: tag)
                }

                Spacer()

                ConfidenceBar(confidence: stock.confidence)
                    .frame(width: 80)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 10)
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .shadow(color: shadowColor, radius: rank <= 3 ? 8 : 4, y: rank <= 3 ? 4 : 2)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(rank <= 3 ? Color.orange.opacity(0.3) : Color.clear, lineWidth: 1.5)
        )
    }

    private var shadowColor: Color {
        rank <= 3 ? Color.orange.opacity(0.12) : Color.black.opacity(0.05)
    }

    private func scoreColor(_ score: Double) -> Color {
        if score >= 80 { return .red }
        if score >= 60 { return .orange }
        if score >= 40 { return .yellow }
        return .gray
    }
}

// MARK: - 排名徽章

struct RankBadge: View {
    let rank: Int
    let isNew: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(rankColor)
                .frame(width: 32, height: 32)

            if isNew {
                Text("新")
                    .font(.system(size: 10, weight: .black))
                    .foregroundStyle(.white)
            } else {
                Text("\(rank)")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(rank <= 3 ? .white : .primary)
            }
        }
        .overlay(alignment: .topTrailing) {
            if rank <= 3 && !isNew {
                Circle()
                    .fill(.yellow)
                    .frame(width: 8, height: 8)
                    .offset(x: 2, y: -2)
            }
        }
    }

    private var rankColor: Color {
        if isNew { return .purple }
        switch rank {
        case 1: return .orange
        case 2: return .orange.opacity(0.7)
        case 3: return .orange.opacity(0.5)
        default: return Color(.systemGray5)
        }
    }
}

// MARK: - 信号标签

struct SignalTagView: View {
    let tag: String

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.system(size: 8))
            Text(tag)
                .font(.system(size: 10))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(tagColor.opacity(0.12))
        .foregroundStyle(tagColor)
        .clipShape(Capsule())
    }

    private var icon: String {
        switch tag {
        case "资金流入": return "banknote"
        case "政策催化": return "building.2"
        case "技术突破": return "chart.line.uptrend.xyaxis"
        case "情绪反转": return "brain"
        case "北向增持": return "globe.asia.australia"
        default: return "tag"
        }
    }

    private var tagColor: Color {
        switch tag {
        case "资金流入": return .blue
        case "政策催化": return .purple
        case "技术突破": return .orange
        case "情绪反转": return .pink
        case "北向增持": return .teal
        default: return .gray
        }
    }
}

// MARK: - 置信度条

struct ConfidenceBar: View {
    let confidence: Double

    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text("置信度 \(Int(confidence * 100))%")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color(.systemGray5))
                        .frame(height: 4)
                    Capsule()
                        .fill(confidence > 0.6 ? Color.green : confidence > 0.4 ? Color.orange : Color.red)
                        .frame(width: geo.size.width * confidence, height: 4)
                }
            }
            .frame(height: 4)
        }
    }
}

struct MarketTag: View {
    let text: String
    let color: Color

    init(_ text: String, color: Color) {
        self.text = text
        self.color = color
    }

    var body: some View {
        Text(text)
            .font(.system(size: 9))
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .clipShape(RoundedRectangle(cornerRadius: 3))
    }
}

// MARK: - 数据模型

struct RankedStock: Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let symbol: String
    let market: String
    let industry: String
    let latestPrice: Double?
    let latestChange: Double?
    let direction: String
    let confidence: Double
    let overallScore: Double
    let signalTags: [String]
    let factorScores: FactorScores
}

struct FactorScores {
    let momentum: Double
    let value: Double
    let quality: Double
    let sentiment: Double
    let technical: Double
}

// MARK: - ViewModel

@MainActor
final class RankedPoolViewModel: ObservableObject {
    @Published var rankedStocks: [RankedStock] = []
    @Published var isLoading = false
    @Published var newAdditions: Set<String> = []
    @Published var isUsingMockData = false

    private let api = APIClient.shared
    var isOffline: Bool = false

    func loadRankedPool() async {
        isLoading = true
        defer { isLoading = false }

        // 1. 优先调用后端 API
        if !isOffline {
            do {
                let pool = try await api.fetchDailyPool()
                if !pool.isEmpty {
                    isUsingMockData = false
                    rankedStocks = pool.map { ps in
                        RankedStock(
                            code: ps.code, name: ps.name,
                            symbol: ps.code.replacingOccurrences(of: ".SH", with: "").replacingOccurrences(of: ".SZ", with: ""),
                            market: "", industry: "",
                            latestPrice: nil, latestChange: nil,
                            direction: ps.direction, confidence: ps.confidence,
                            overallScore: ps.overallScore ?? 50,
                            signalTags: ps.signalTags ?? [],
                            factorScores: FactorScores(momentum: 50, value: 50, quality: 50, sentiment: 50, technical: 50)
                        )
                    }
                    return
                }
            } catch {
                // 后端不可用，降级
            }
        }

        // 2. 降级：本地CoreML推理 或 Mock数据
        // TODO: 从SwiftData加载自选股的PriceHistory，本地CoreML推理排序
        isUsingMockData = true
        rankedStocks = generateMockRankings()
    }

    func refresh() async {
        newAdditions = []
        await loadRankedPool()
    }

    private func generateMockRankings() -> [RankedStock] {
        let stocks: [(String, String, String, String)] = [
            ("600519.SH", "贵州茅台", "白酒", "沪"),
            ("000858.SZ", "五粮液", "白酒", "深"),
            ("300750.SZ", "宁德时代", "电气设备", "创业"),
            ("000001.SZ", "平安银行", "银行", "深"),
            ("601318.SH", "中国平安", "保险", "沪"),
            ("002594.SZ", "比亚迪", "汽车", "深"),
            ("688981.SH", "中芯国际", "半导体", "科创"),
            ("600036.SH", "招商银行", "银行", "沪"),
            ("000333.SZ", "美的集团", "家电", "深"),
            ("601012.SH", "隆基绿能", "光伏", "沪"),
        ]

        let tags = [
            ["资金流入", "北向增持"],
            ["技术突破"],
            ["政策催化", "资金流入"],
            ["情绪反转"],
            ["资金流入"],
            ["技术突破", "政策催化"],
            ["北向增持", "政策催化"],
            ["资金流入"],
            ["情绪反转"],
            ["技术突破"],
        ]

        return zip(stocks, tags).enumerated().map { i, pair in
            let (code, name, industry, market) = pair.0
            let score = Double(95 - i * 5 - Int.random(in: 0...3))
            return RankedStock(
                code: code,
                name: name,
                symbol: code.replacingOccurrences(of: ".SH", with: "")
                          .replacingOccurrences(of: ".SZ", with: ""),
                market: market,
                industry: industry,
                latestPrice: Double.random(in: 10...300),
                latestChange: Double.random(in: -3...5),
                direction: i < 6 ? "up" : "down",
                confidence: Double.random(in: 0.55...0.85),
                overallScore: score,
                signalTags: pair.1,
                factorScores: FactorScores(
                    momentum: Double.random(in: 30...90),
                    value: Double.random(in: 20...85),
                    quality: Double.random(in: 40...95),
                    sentiment: Double.random(in: 25...88),
                    technical: Double.random(in: 35...92)
                )
            )
        }
    }
}

#Preview {
    RankedPoolView()
}
