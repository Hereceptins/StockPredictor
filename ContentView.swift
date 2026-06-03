import SwiftUI

/// 主TabView —— 大盘 | 行情 | 精选 | 持仓 | 设置
struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView(selection: $appState.selectedTab) {
            MarketOverviewView()
                .tabItem {
                    Label(AppState.Tab.overview.rawValue,
                          systemImage: AppState.Tab.overview.icon)
                }
                .tag(AppState.Tab.overview)

            MarketView()
                .tabItem {
                    Label(AppState.Tab.market.rawValue,
                          systemImage: AppState.Tab.market.icon)
                }
                .tag(AppState.Tab.market)

            RankedPoolView()
                .tabItem {
                    Label(AppState.Tab.pool.rawValue,
                          systemImage: AppState.Tab.pool.icon)
                }
                .tag(AppState.Tab.pool)

            PortfolioView()
                .tabItem {
                    Label(AppState.Tab.portfolio.rawValue,
                          systemImage: AppState.Tab.portfolio.icon)
                }
                .tag(AppState.Tab.portfolio)

            SettingsView()
                .tabItem {
                    Label(AppState.Tab.settings.rawValue,
                          systemImage: AppState.Tab.settings.icon)
                }
                .tag(AppState.Tab.settings)
        }
        .tint(.orange)
    }
}

// MARK: - 行情页（搜索+自选股）

struct MarketView: View {
    @State private var searchText = ""
    @State private var showSearch = false

    var body: some View {
        NavigationStack {
            WatchlistView()
                .navigationTitle("自选股")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showSearch = true
                        } label: {
                            Image(systemName: "magnifyingglass")
                        }
                    }
                }
                .searchable(text: $searchText, placement: .navigationBarDrawer,
                            prompt: "搜索股票代码或名称")
                .sheet(isPresented: $showSearch) {
                    SearchView()
                }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppState())
}
