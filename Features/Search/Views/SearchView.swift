import SwiftUI
import SwiftData

/// 股票搜索视图
struct SearchView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext
    @StateObject private var vm = SearchViewModel()
    @State private var query = ""

    var body: some View {
        NavigationStack {
            List {
                if query.isEmpty {
                    Section("热门搜索") {
                        ForEach(vm.hotStocks, id: \.code) { stock in
                            SearchResultRow(stock: stock) {
                                addToWatchlist(stock)
                            }
                        }
                    }
                } else if vm.isSearching {
                    HStack {
                        Spacer()
                        ProgressView("搜索中...")
                        Spacer()
                    }
                } else if vm.results.isEmpty {
                    ContentUnavailableView.search(text: query)
                } else {
                    Section("搜索结果") {
                        ForEach(vm.results, id: \.code) { stock in
                            SearchResultRow(stock: stock) {
                                addToWatchlist(stock)
                            }
                        }
                    }
                }
            }
            .navigationTitle("添加自选")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query, placement: .navigationBarDrawer, prompt: "输入代码或名称")
            .onChange(of: query) { _, newValue in
                vm.search(query: newValue)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    private func addToWatchlist(_ stock: StockItem) {
        // 避免重复
        let code = stock.code
        let descriptor = FetchDescriptor<WatchlistItem>(
            predicate: #Predicate { $0.stock?.code == code }
        )
        if let existing = try? modelContext.fetch(descriptor), !existing.isEmpty {
            return
        }

        stock.isWatchlisted = true
        let count = (try? modelContext.fetch(FetchDescriptor<WatchlistItem>()).count) ?? 0
        let item = WatchlistItem(order: count, stock: stock)
        modelContext.insert(item)
    }
}

struct SearchResultRow: View {
    let stock: StockItem
    let onAdd: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(stock.name)
                    .font(.body)
                Text("\(stock.symbol) · \(stock.industry ?? "未知行业")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                onAdd()
            } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.title3)
                    .foregroundStyle(.orange)
            }
        }
    }
}

// MARK: - ViewModel

@MainActor
final class SearchViewModel: ObservableObject {
    @Published var results: [StockItem] = []
    @Published var isSearching = false

    let hotStocks: [StockItem] = [
        StockItem(code: "600519.SH", name: "贵州茅台", market: "SH", industry: "白酒"),
        StockItem(code: "000858.SZ", name: "五粮液", market: "SZ", industry: "白酒"),
        StockItem(code: "300750.SZ", name: "宁德时代", market: "SZ", industry: "电气设备"),
        StockItem(code: "000001.SZ", name: "平安银行", market: "SZ", industry: "银行"),
        StockItem(code: "601318.SH", name: "中国平安", market: "SH", industry: "保险"),
    ]

    func search(query: String) {
        guard query.count >= 1 else {
            results = []
            return
        }
        isSearching = true
        // TODO: 调用后端搜索API
        Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            // 模拟结果
            let local = hotStocks.filter {
                $0.name.contains(query) || $0.symbol.contains(query)
            }
            results = local
            isSearching = false
        }
    }
}

#Preview {
    SearchView()
}
