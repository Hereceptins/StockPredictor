import SwiftUI

/// 大盘概览 —— 参考同花顺风格设计
struct MarketOverviewView: View {
    @StateObject private var vm = MarketOverviewViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                // 指数卡片行
                IndexCardRow(indices: vm.indices)

                // 市场热度
                MarketHeatCard(
                    upCount: vm.upCount,
                    downCount: vm.downCount,
                    flatCount: vm.flatCount,
                    limitUpCount: vm.limitUpCount,
                    limitDownCount: vm.limitDownCount
                )

                // 行业板块
                SectorHeatmapView(sectors: vm.sectors)

                // 涨幅榜
                TopMoversView(title: "涨幅榜", stocks: vm.topGainers, color: .red)

                // 跌幅榜
                TopMoversView(title: "跌幅榜", stocks: vm.topLosers, color: .green)

                // 成交额榜
                TopMoversView(title: "成交额榜", stocks: vm.topVolume, color: .blue)
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
        .task { await vm.loadData() }
    }
}

// MARK: - 指数卡片行

struct IndexCardRow: View {
    let indices: [MarketIndex]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(indices) { index in
                    IndexCard(index: index)
                }
            }
        }
    }
}

struct IndexCard: View {
    let index: MarketIndex

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(index.name)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(String(format: "%.2f", index.value))
                .font(.title3.bold().monospacedDigit())
            HStack(spacing: 4) {
                Text(String(format: "%+.2f", index.change))
                Text(String(format: "%+.2f%%", index.changePct))
                    .font(.caption)
            }
            .font(.subheadline.monospacedDigit())
            .foregroundStyle(index.change >= 0 ? .red : .green)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(width: 150, alignment: .leading)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.04), radius: 4)
    }
}

struct MarketIndex: Identifiable {
    let id = UUID()
    let code: String
    let name: String
    let value: Double
    let change: Double
    let changePct: Double
}

// MARK: - 市场热度卡片

struct MarketHeatCard: View {
    let upCount: Int
    let downCount: Int
    let flatCount: Int
    let limitUpCount: Int
    let limitDownCount: Int

    var total: Int { upCount + downCount + flatCount }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("市场热度")
                    .font(.headline)
                Spacer()
                Text("共\(total)只")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // 涨跌分布条
            GeometryReader { geo in
                HStack(spacing: 0) {
                    Rectangle()
                        .fill(Color.red)
                        .frame(width: geo.size.width * Double(upCount) / Double(max(total, 1)))
                    Rectangle()
                        .fill(Color.gray)
                        .frame(width: geo.size.width * Double(flatCount) / Double(max(total, 1)))
                    Rectangle()
                        .fill(Color.green)
                        .frame(width: geo.size.width * Double(downCount) / Double(max(total, 1)))
                }
            }
            .frame(height: 8)
            .clipShape(RoundedRectangle(cornerRadius: 4))

            // 数据行
            HStack(spacing: 16) {
                MarketStat(color: .red, label: "上涨", value: "\(upCount)")
                MarketStat(color: .gray, label: "平盘", value: "\(flatCount)")
                MarketStat(color: .green, label: "下跌", value: "\(downCount)")
                MarketStat(color: .orange, label: "涨停", value: "\(limitUpCount)")
                MarketStat(color: .blue, label: "跌停", value: "\(limitDownCount)")
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct MarketStat: View {
    let color: Color
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.bold())
        }
    }
}

// MARK: - 行业板块热力图

struct SectorHeatmapView: View {
    let sectors: [SectorItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("行业板块")
                .font(.headline)

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                ForEach(sectors.prefix(12)) { sector in
                    SectorBlock(sector: sector)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct SectorBlock: View {
    let sector: SectorItem

    var body: some View {
        VStack(spacing: 2) {
            Text(sector.name)
                .font(.system(size: 11))
                .lineLimit(1)
            Text(String(format: "%+.2f%%", sector.changePct))
                .font(.system(size: 13, weight: .bold).monospacedDigit())
                .foregroundStyle(sector.changePct >= 0 ? .red : .green)
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(
            (sector.changePct >= 0 ? Color.red : Color.green)
                .opacity(abs(sector.changePct) / 10)
        )
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct SectorItem: Identifiable {
    let id = UUID()
    let name: String
    let changePct: Double
}

// MARK: - 涨跌幅/成交额榜

struct TopMoversView: View {
    let title: String
    let stocks: [MoverStock]
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)

            ForEach(Array(stocks.prefix(5).enumerated()), id: \.element.id) { i, stock in
                HStack(spacing: 10) {
                    Text("\(i + 1)")
                        .font(.caption.bold())
                        .foregroundStyle(i < 3 ? color : .secondary)
                        .frame(width: 18)

                    Text(stock.name)
                        .font(.subheadline)
                        .lineLimit(1)

                    Text(stock.code)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Spacer()

                    Text(String(format: "%+.2f%%", stock.changePct))
                        .font(.subheadline.bold().monospacedDigit())
                        .foregroundStyle(stock.changePct >= 0 ? .red : .green)
                        .frame(width: 70, alignment: .trailing)
                }
                .padding(.vertical, 3)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

struct MoverStock: Identifiable {
    let id = UUID()
    let code: String
    let name: String
    let changePct: Double
    let volume: Double?
}

// MARK: - ViewModel

@MainActor
final class MarketOverviewViewModel: ObservableObject {
    @Published var indices: [MarketIndex] = []
    @Published var upCount = 0; @Published var downCount = 0; @Published var flatCount = 0
    @Published var limitUpCount = 0; @Published var limitDownCount = 0
    @Published var sectors: [SectorItem] = []
    @Published var topGainers: [MoverStock] = []
    @Published var topLosers: [MoverStock] = []
    @Published var topVolume: [MoverStock] = []

    func loadData() async {
        // TODO: 从后端API加载实时数据
        indices = [
            MarketIndex(code: "000001", name: "上证指数", value: 3086.81, change: -4.86, changePct: -0.16),
            MarketIndex(code: "399001", name: "深证成指", value: 11098.99, change: 45.21, changePct: 0.41),
            MarketIndex(code: "399006", name: "创业板指", value: 2376.42, change: -11.49, changePct: -0.48),
            MarketIndex(code: "000688", name: "科创50", value: 745.30, change: 3.67, changePct: 0.49),
        ]
        upCount = 2145; downCount = 2780; flatCount = 356
        limitUpCount = 48; limitDownCount = 12

        sectors = [
            SectorItem(name: "半导体", changePct: 3.21),
            SectorItem(name: "汽车", changePct: 2.15),
            SectorItem(name: "白酒", changePct: -1.82),
            SectorItem(name: "银行", changePct: 0.52),
            SectorItem(name: "光伏", changePct: -3.45),
            SectorItem(name: "医药", changePct: -1.20),
            SectorItem(name: "AI", changePct: 4.56),
            SectorItem(name: "券商", changePct: 1.08),
            SectorItem(name: "地产", changePct: -2.67),
            SectorItem(name: "煤炭", changePct: 0.89),
            SectorItem(name: "军工", changePct: -0.34),
            SectorItem(name: "电力", changePct: 1.75),
        ]

        topGainers = (0..<5).map { i in
            MoverStock(code: "60\(1000+i).SH", name: ["贵州茅台","宁德时代","比亚迪","中芯国际","招商银行"][i], changePct: Double.random(in: 5...10), volume: nil)
        }

        topLosers = (0..<5).map { i in
            MoverStock(code: "00\(2000+i).SZ", name: ["隆基绿能","万科A","中国中免","药明康德","东方财富"][i], changePct: Double.random(in: -10...(-5)), volume: nil)
        }

        topVolume = (0..<5).map { i in
            MoverStock(code: "60\(3000+i).SH", name: ["贵州茅台","宁德时代","中信证券","中国平安","五粮液"][i], changePct: Double.random(in: -3...3), volume: Double.random(in: 30...80) * 1e8)
        }
    }
}

#Preview {
    MarketOverviewView()
}
