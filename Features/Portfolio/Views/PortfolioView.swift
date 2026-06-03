import SwiftUI
import Charts

/// 个人中心 —— 持仓收益 + 资产总览
struct PortfolioView: View {
    @StateObject private var vm = PortfolioViewModel()
    @State private var selectedTab: PortfolioTab = .holdings

    enum PortfolioTab: String, CaseIterable {
        case holdings = "持仓"
        case history = "收益"
        case accuracy = "预测"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // 资产总览卡片
                    AssetOverviewCard(
                        totalValue: vm.totalValue,
                        todayChange: vm.todayChange,
                        todayChangePct: vm.todayChangePct,
                        totalReturn: vm.totalReturn,
                        totalReturnPct: vm.totalReturnPct
                    )

                    // Tab切换
                    Picker("", selection: $selectedTab) {
                        ForEach(PortfolioTab.allCases, id: \.self) { t in
                            Text(t.rawValue).tag(t)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal)

                    switch selectedTab {
                    case .holdings:
                        HoldingsList(holdings: vm.holdings)
                    case .history:
                        ReturnChart(returns: vm.dailyReturns)
                    case .accuracy:
                        PredictionAccuracyView(accuracy: vm.predictionAccuracy)
                    }
                }
                .padding(.bottom, 100)
            }
            .navigationTitle("我的")
            .background(Color(.systemGroupedBackground))
            .task { await vm.loadData() }
            .refreshable { await vm.refresh() }
        }
    }
}

// MARK: - 资产总览卡片

struct AssetOverviewCard: View {
    let totalValue: Double
    let todayChange: Double
    let todayChangePct: Double
    let totalReturn: Double
    let totalReturnPct: Double

    var body: some View {
        VStack(spacing: 0) {
            // 总资产
            VStack(spacing: 4) {
                Text("总资产（模拟）")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(String(format: "¥%.2f", totalValue))
                    .font(.system(size: 36, weight: .bold, design: .rounded).monospacedDigit())
            }
            .padding(.top, 20)

            // 今日盈亏
            HStack(spacing: 24) {
                StatBadge(
                    title: "今日盈亏",
                    value: String(format: "%+.2f", todayChange),
                    pct: String(format: "%+.2f%%", todayChangePct),
                    isPositive: todayChange >= 0
                )
                StatBadge(
                    title: "累计盈亏",
                    value: String(format: "%+.2f", totalReturn),
                    pct: String(format: "%+.2f%%", totalReturnPct),
                    isPositive: totalReturn >= 0
                )
            }
            .padding(.vertical, 16)

            Divider().padding(.horizontal)

            // 快捷指标
            HStack(spacing: 0) {
                QuickMetric(label: "持仓数", value: "6只")
                QuickMetric(label: "今日胜率", value: "66.7%")
                QuickMetric(label: "AI预测准确率", value: "58.3%")
                QuickMetric(label: "风险等级", value: "中")
            }
            .padding(.vertical, 12)
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
        .padding(.horizontal)
    }
}

struct StatBadge: View {
    let title: String
    let value: String
    let pct: String
    let isPositive: Bool

    var body: some View {
        VStack(spacing: 2) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.bold().monospacedDigit())
                .foregroundStyle(isPositive ? .red : .green)
            Text(pct)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(isPositive ? .red : .green)
        }
        .frame(maxWidth: .infinity)
    }
}

struct QuickMetric: View {
    let label: String
    let value: String

    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.subheadline.bold())
            Text(label)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - 持仓列表

struct HoldingsList: View {
    let holdings: [HoldingItem]

    var body: some View {
        VStack(spacing: 10) {
            ForEach(holdings) { holding in
                HoldingRow(holding: holding)
            }
        }
        .padding(.horizontal)
    }
}

struct HoldingItem: Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let shares: Int
    let costPrice: Double
    let currentPrice: Double
    let profitLoss: Double
    let profitLossPct: Double
    let weight: Double  // 仓位占比
    let hasAIRecommendation: Bool
    let aiDirection: String?
}

struct HoldingRow: View {
    let holding: HoldingItem

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                // 股票信息
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(holding.name)
                            .font(.subheadline.bold())
                        if holding.hasAIRecommendation {
                            Image(systemName: "sparkles")
                                .font(.system(size: 10))
                                .foregroundStyle(.orange)
                        }
                    }
                    Text(holding.code)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // 盈亏
                VStack(alignment: .trailing, spacing: 2) {
                    Text(String(format: "¥%.2f", holding.currentPrice))
                        .font(.subheadline.monospacedDigit())
                    HStack(spacing: 3) {
                        Text(String(format: "%+.2f", holding.profitLoss))
                        Text(String(format: "%+.2f%%", holding.profitLossPct))
                            .font(.caption)
                    }
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(holding.profitLoss >= 0 ? .red : .green)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            // 底部进度条（仓位占比）
            HStack(spacing: 6) {
                Text("仓位")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color(.systemGray6))
                            .frame(height: 3)
                        Capsule()
                            .fill(holding.profitLoss >= 0 ? Color.red.opacity(0.6) : Color.green.opacity(0.6))
                            .frame(width: geo.size.width * holding.weight, height: 3)
                    }
                }
                .frame(height: 3)

                Text(String(format: "%.1f%%", holding.weight * 100))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 10)
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.03), radius: 4, y: 1)
    }
}

// MARK: - 收益曲线

struct ReturnChart: View {
    let returns: [DailyReturn]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if returns.isEmpty {
                ContentUnavailableView("暂无收益数据", systemImage: "chart.xyaxis.line")
            } else {
                Chart(returns) { point in
                    LineMark(
                        x: .value("日期", point.date),
                        y: .value("收益率", point.cumulativeReturn)
                    )
                    .foregroundStyle(
                        (point.cumulativeReturn >= 0 ? Color.red : Color.green).gradient
                    )

                    AreaMark(
                        x: .value("日期", point.date),
                        y: .value("收益率", point.cumulativeReturn)
                    )
                    .foregroundStyle(
                        (point.cumulativeReturn >= 0 ? Color.red : Color.green)
                            .opacity(0.1)
                            .gradient
                    )
                }
                .frame(height: 200)
                .chartYAxis {
                    AxisMarks()
                }
                .padding()
            }

            // 统计
            HStack(spacing: 20) {
                StatItem(label: "年化收益", value: "--%")
                StatItem(label: "夏普比率", value: "--")
                StatItem(label: "最大回撤", value: "--%")
                StatItem(label: "跑赢沪深300", value: "--%")
            }
            .padding()
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }
}

struct DailyReturn: Identifiable {
    let id = UUID()
    let date: Date
    let return_: Double
    let cumulativeReturn: Double
}

// MARK: - 预测准确率

struct PredictionAccuracyView: View {
    let accuracy: AccuracyStats

    var body: some View {
        VStack(spacing: 16) {
            // 总体准确率环形图
            ZStack {
                Circle()
                    .stroke(Color(.systemGray5), lineWidth: 10)
                    .frame(width: 100, height: 100)

                Circle()
                    .trim(from: 0, to: accuracy.overall / 100)
                    .stroke(
                        accuracy.overall >= 55 ? Color.red : Color.gray,
                        style: StrokeStyle(lineWidth: 10, lineCap: .round)
                    )
                    .frame(width: 100, height: 100)
                    .rotationEffect(.degrees(-90))

                VStack(spacing: 0) {
                    Text(String(format: "%.1f%%", accuracy.overall))
                        .font(.title2.bold())
                    Text("准确率")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.top)

            Text(accuracy.overall >= 55
                 ? "AI模型表现优于随机猜测（50%），具有一定的预测能力"
                 : "AI模型正在持续优化中，当前准确率仅供参考")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            // 逐月准确率
            HStack(spacing: 12) {
                AccuracyMonthBar(month: "1月", rate: accuracy.monthly["1月"] ?? 0)
                AccuracyMonthBar(month: "2月", rate: accuracy.monthly["2月"] ?? 0)
                AccuracyMonthBar(month: "3月", rate: accuracy.monthly["3月"] ?? 0)
                AccuracyMonthBar(month: "4月", rate: accuracy.monthly["4月"] ?? 0)
                AccuracyMonthBar(month: "5月", rate: accuracy.monthly["5月"] ?? 0)
                AccuracyMonthBar(month: "6月", rate: accuracy.monthly["6月"] ?? 0)
            }
            .padding()
        }
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal)
    }
}

struct AccuracyMonthBar: View {
    let month: String
    let rate: Double

    var body: some View {
        VStack(spacing: 4) {
            Text(String(format: "%.0f%%", rate))
                .font(.caption2.bold())
                .foregroundStyle(rate >= 55 ? .red : .gray)
            GeometryReader { geo in
                VStack {
                    Spacer()
                    RoundedRectangle(cornerRadius: 2)
                        .fill(rate >= 55 ? Color.red : Color.gray.opacity(0.4))
                        .frame(height: geo.size.height * rate / 100)
                }
            }
            .frame(width: 30)
            Text(month)
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
        }
    }
}

struct AccuracyStats {
    let overall: Double
    let monthly: [String: Double]
    let totalPredictions: Int
    let correctPredictions: Int
}

// MARK: - ViewModel

@MainActor
final class PortfolioViewModel: ObservableObject {
    @Published var totalValue: Double = 100_000.00
    @Published var todayChange: Double = 1_250.80
    @Published var todayChangePct: Double = 1.25
    @Published var totalReturn: Double = 5_680.30
    @Published var totalReturnPct: Double = 6.02
    @Published var holdings: [HoldingItem] = []
    @Published var dailyReturns: [DailyReturn] = []
    @Published var predictionAccuracy = AccuracyStats(
        overall: 58.3,
        monthly: ["1月": 55, "2月": 62, "3月": 51, "4月": 60, "5月": 57, "6月": 63],
        totalPredictions: 120,
        correctPredictions: 70
    )

    func loadData() async {
        // TODO: 从SwiftData加载持仓 + 计算收益
        holdings = mockHoldings()
        dailyReturns = mockReturns()
    }

    func refresh() async {
        await loadData()
    }

    private func mockHoldings() -> [HoldingItem] {
        [
            HoldingItem(code: "600519.SH", name: "贵州茅台", shares: 100, costPrice: 1680, currentPrice: 1750, profitLoss: 7000, profitLossPct: 4.17, weight: 0.30, hasAIRecommendation: true, aiDirection: "up"),
            HoldingItem(code: "300750.SZ", name: "宁德时代", shares: 200, costPrice: 185, currentPrice: 192, profitLoss: 1400, profitLossPct: 3.78, weight: 0.25, hasAIRecommendation: true, aiDirection: "up"),
            HoldingItem(code: "000858.SZ", name: "五粮液", shares: 150, costPrice: 142, currentPrice: 138, profitLoss: -600, profitLossPct: -2.82, weight: 0.20, hasAIRecommendation: false, aiDirection: nil),
            HoldingItem(code: "000001.SZ", name: "平安银行", shares: 500, costPrice: 10.5, currentPrice: 10.8, profitLoss: 150, profitLossPct: 2.86, weight: 0.15, hasAIRecommendation: true, aiDirection: "up"),
            HoldingItem(code: "601012.SH", name: "隆基绿能", shares: 300, costPrice: 18, currentPrice: 17.2, profitLoss: -240, profitLossPct: -4.44, weight: 0.10, hasAIRecommendation: false, aiDirection: "down"),
        ]
    }

    private func mockReturns() -> [DailyReturn] {
        let calendar = Calendar.current
        let today = Date()
        var cumulative = 0.0
        return (0..<60).map { i in
            let date = calendar.date(byAdding: .day, value: -59 + i, to: today)!
            let daily = Double.random(in: -0.025...0.03)
            cumulative += daily
            return DailyReturn(date: date, return_: daily, cumulativeReturn: cumulative)
        }
    }
}

#Preview {
    PortfolioView()
}
