import SwiftUI
import SwiftData

/// 自选股列表
struct WatchlistView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \WatchlistItem.order) private var watchlist: [WatchlistItem]
    @State private var isRefreshing = false

    var body: some View {
        List {
            if watchlist.isEmpty {
                ContentUnavailableView(
                    "暂无自选股",
                    systemImage: "star",
                    description: Text("搜索并添加您关注的股票")
                )
            } else {
                ForEach(watchlist) { item in
                    if let stock = item.stock {
                        NavigationLink(destination: StockDetailView(stock: stock)) {
                            WatchlistRow(stock: stock)
                        }
                        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                            Button(role: .destructive) {
                                removeFromWatchlist(item)
                            } label: {
                                Label("删除", systemImage: "star.slash")
                            }
                        }
                    }
                }
                .onMove { source, destination in
                    var items = watchlist.sorted { $0.order < $1.order }
                    items.move(fromOffsets: source, toOffset: destination)
                    for (i, item) in items.enumerated() {
                        item.order = i
                    }
                }
            }
        }
        .refreshable { await refreshQuotes() }
    }

    private func removeFromWatchlist(_ item: WatchlistItem) {
        if let stock = item.stock {
            stock.isWatchlisted = false
        }
        modelContext.delete(item)
    }

    private func refreshQuotes() async {
        isRefreshing = true
        // TODO: 调用后端API刷新行情
        try? await Task.sleep(nanoseconds: 1_000_000_000)
        isRefreshing = false
    }
}

/// 自选股行组件
struct WatchlistRow: View {
    let stock: StockItem

    var body: some View {
        HStack(spacing: 12) {
            // 左侧信息
            VStack(alignment: .leading, spacing: 4) {
                Text(stock.name)
                    .font(.headline)
                HStack(spacing: 6) {
                    Text(stock.symbol)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(stock.marketShort)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(marketColor.opacity(0.15))
                        .foregroundStyle(marketColor)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }

            Spacer()

            // 右侧价格
            VStack(alignment: .trailing, spacing: 4) {
                if let price = stock.latestPrice {
                    Text(String(format: "%.2f", price))
                        .font(.headline.monospacedDigit())
                }

                if let change = stock.latestChange {
                    Text(String(format: "%+.2f%%", change))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(change >= 0 ? .red : .green)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background((change >= 0 ? Color.red : Color.green).opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var marketColor: Color {
        if stock.code.hasPrefix("688") { return .purple }
        if stock.code.hasPrefix("300") || stock.code.hasPrefix("301") { return .blue }
        return .orange
    }
}

#Preview {
    NavigationStack {
        WatchlistView()
    }
}
