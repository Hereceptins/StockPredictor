import Foundation
import SwiftData

/// 每日精选池 ViewModel
@MainActor
final class PoolViewModel: ObservableObject {
    @Published var stocks: [StockItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var poolDate: Date?

    private let api = APIClient.shared
    private let predictionService = PredictionService.shared
    var isOffline: Bool = false

    /// 加载每日精选池
    func loadDailyPool() async {
        isLoading = true
        errorMessage = nil

        do {
            // 从环境注入的isOffline获取（非新建AppState实例）
            if !isOffline {
                let poolStocks = try? await api.fetchDailyPool()
                if let pool = poolStocks, !pool.isEmpty {
                    stocks = pool.map { ps in
                        let stock = StockItem(code: ps.code, name: ps.name, market: "")
                        stock.latestPrice = nil
                        stock.latestChange = nil
                        return stock
                    }
                    poolDate = Date()
                }
            }

            // 如果后端不可用或离线，使用本地模型
            if stocks.isEmpty {
                try await generateLocalPool()
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    /// 本地模型生成精选池（离线可用）
    private func generateLocalPool() async throws {
        // TODO: 从SwiftData读取自选股，本地CoreML推理排序
        // 当前为MVP占位
        stocks = []
    }

    /// 下拉刷新
    func refresh() async {
        await loadDailyPool()
    }

    /// 获取某只股票的预测
    func predict(for stock: StockItem,
                 priceHistory: [PriceHistory]) async -> PredictionRecord? {
        try? await predictionService.predictPriceDirection(for: stock, priceHistory: priceHistory)
    }
}

/// 持仓体检 ViewModel
@MainActor
final class PortfolioHealthViewModel: ObservableObject {
    @Published var riskAlerts: [RiskAlert] = []
    @Published var overallRisk: RiskLevel = .low

    enum RiskLevel: String {
        case low = "低风险"
        case medium = "中风险"
        case high = "高风险"
    }

    struct RiskAlert: Identifiable {
        let id = UUID()
        let stock: StockItem
        let alertType: AlertType
        let message: String
    }

    enum AlertType {
        case limitUnlock    // 限售股解禁
        case earningsReport // 业绩预告
        case policyEvent    // 政策事件
        case anomaly        // 异常波动
        case marginCall     // 两融预警
    }
}
