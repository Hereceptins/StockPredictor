import Foundation
import SwiftData
import BackgroundTasks

/// 数据同步服务 —— 后台刷新行情 + 更新模型
final class DataSyncService: @unchecked Sendable {
    static let shared = DataSyncService()

    private let api = APIClient.shared
    private var modelContext: ModelContext?
    private let bgTaskIdentifier = "com.stockpredictor.refresh"

    // MARK: - 后台任务注册

    func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: bgTaskIdentifier, using: nil) { task in
            self.handleBackgroundRefresh(task: task as! BGAppRefreshTask)
        }
    }

    func scheduleBackgroundRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: bgTaskIdentifier)
        // 交易日收盘后刷新（16:00）
        request.earliestBeginDate = Calendar.current.date(bySettingHour: 16, minute: 0, second: 0, of: Date())
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handleBackgroundRefresh(task: BGAppRefreshTask) {
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }

        Task {
            await refreshQuotes()
            await checkModelUpdate()
            task.setTaskCompleted(success: true)
            scheduleBackgroundRefresh()  // 安排下次刷新
        }
    }

    // MARK: - 行情刷新

    func refreshQuotes() async {
        // 从SwiftData获取所有自选股
        guard let context = modelContext else { return }

        do {
            let descriptor = FetchDescriptor<WatchlistItem>()
            let watchlist = try context.fetch(descriptor)

            for item in watchlist {
                guard let stock = item.stock else { continue }

                // 获取最新行情
                let today = ISO8601DateFormatter().string(from: Date())
                let kline = try? await api.fetchKLine(
                    code: stock.code,
                    start: today,
                    end: today
                )

                if let latest = kline?.last {
                    stock.latestPrice = latest.close
                    stock.latestChange = latest.pctChange
                    stock.lastUpdated = Date()
                }
            }

            try context.save()
        } catch {
            print("[DataSync] Refresh failed: \(error)")
        }
    }

    // MARK: - 模型更新

    func checkModelUpdate() async {
        let hasUpdate = await PredictionService.shared.modelManager.checkForUpdate()

        if hasUpdate {
            // 下载新模型
            let info = try? await api.checkModelVersion()
            if let urlString = info?.downloadURL, let url = URL(string: urlString) {
                try? await PredictionService.shared.modelManager.downloadModel(
                    from: url, name: "StockRankingModel"
                )
                // 重新加载
                await MainActor.run {
                    PredictionService.shared.loadModels()
                }
            }
        }
    }

    // MARK: - 每日精选池刷新

    func refreshDailyPool() async throws -> [PoolStock] {
        // 收盘后调用后端获取当日精选池
        let pool = try await api.fetchDailyPool()

        // 存入SwiftData
        guard let context = modelContext else { return pool }

        for ps in pool {
            let stock = StockItem(code: ps.code, name: ps.name, market: "")
            let prediction = PredictionRecord(
                baseDate: Date(),
                targetDate: TradingCalendar.shared.nextTradingDay(from: Date(), offset: 3)
                    ?? Calendar.current.date(byAdding: .day, value: 5, to: Date())!,
                direction: ps.direction,
                confidence: ps.confidence,
                modelVersion: PredictionService.shared.modelManager.currentVersion,
                stock: stock
            )
            prediction.signalTags = ps.signalTags
            context.insert(prediction)
        }

        try context.save()
        return pool
    }

    // MARK: - 历史数据回填

    func backfillHistory(for stock: StockItem) async throws {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyyMMdd"

        let start = dateFormatter.string(from: Calendar.current.date(byAdding: .year, value: -5, to: Date()) ?? Date())
        let end = dateFormatter.string(from: Date())

        let kline = try await api.fetchKLine(
            code: stock.code,
            period: "daily",
            start: start,
            end: end,
            adjust: "fwd"
        )

        guard let context = modelContext else { return }

        for item in kline {
            let df = DateFormatter()
            df.dateFormat = "yyyyMMdd"
            let date = df.date(from: item.date) ?? Date()

            let history = PriceHistory(
                date: date,
                open: item.open,
                high: item.high,
                low: item.low,
                close: item.close,
                volume: item.volume,
                amount: item.amount,
                turnoverRate: item.turnoverRate,
                pctChange: item.pctChange
            )
            history.stock = stock
            context.insert(history)
        }

        try context.save()
    }
}
