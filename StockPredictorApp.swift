import SwiftUI
import SwiftData

/// 智选K线 — A股AI辅助分析工具
/// 每日精选池 + 信号标签 + 风险日历 + 持仓体检
/// 免责声明：所有预测结果仅供参考，不构成投资建议。股市有风险，投资需谨慎。

@main
struct StockPredictorApp: App {
    @StateObject private var appState = AppState()
    @State private var showDisclaimer = true

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .sheet(isPresented: $showDisclaimer) {
                    DisclaimerView(isPresented: $showDisclaimer)
                }
        }
        .modelContainer(for: [
            StockItem.self,
            PriceHistory.self,
            PredictionRecord.self,
            WatchlistItem.self,
        ])
    }
}

// MARK: - 全局应用状态

final class AppState: ObservableObject {
    @Published var selectedTab: Tab = .market
    @Published var isOffline = false
    @Published var lastSyncDate: Date?
    @Published var modelVersion: String = "1.0.0"

    enum Tab: String, CaseIterable {
        case overview = "大盘"
        case market = "行情"
        case pool = "精选"
        case portfolio = "持仓"
        case settings = "设置"

        var icon: String {
            switch self {
            case .overview: "chart.bar.fill"
            case .market: "chart.line.uptrend.xyaxis"
            case .pool: "star.fill"
            case .portfolio: "person.fill"
            case .settings: "gearshape"
            }
        }
    }
}

// MARK: - 免责声明视图

struct DisclaimerView: View {
    @Binding var isPresented: Bool
    @AppStorage("disclaimerAccepted") private var accepted = false

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "exclamationmark.shield.fill")
                .font(.system(size: 56))
                .foregroundColor(.orange)

            Text("风险提示")
                .font(.title.bold())

            Text("""
            本应用为AI辅助数据分析工具，所有预测结果仅供参考，不构成任何投资建议。

            股市有风险，投资需谨慎。历史数据表现不代表未来收益。机器学习模型的预测基于历史数据统计规律，无法预测突发事件、政策变动等不可预见因素。

            数据来源可能包含3-15分钟延迟。请以交易所实时行情为准。

            使用本应用即表示您已充分理解并接受以上风险。
            """)
            .font(.body)
            .multilineTextAlignment(.leading)
            .padding(.horizontal)

            Button {
                accepted = true
                isPresented = false
            } label: {
                Text("我已了解，开始使用")
                    .font(.headline)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.accentColor)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .padding(.horizontal, 40)
        }
        .padding()
        .interactiveDismissDisabled(!accepted)
    }
}
