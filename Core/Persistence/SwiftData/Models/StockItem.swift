import Foundation
import SwiftData

/// A股股票核心数据模型
@Model
final class StockItem {
    /// Tushare格式代码，如 "000001.SZ"
    @Attribute(.unique) var code: String
    /// 股票名称
    var name: String
    /// 市场: SH / SZ / BJ
    var market: String
    /// 申万一级行业
    var industry: String?
    /// 上市日期
    var listDate: Date?
    /// 最新价格
    var latestPrice: Double?
    /// 最新涨跌幅
    var latestChange: Double?
    /// 市值（亿元）
    var marketCap: Double?
    /// PE
    var pe: Double?
    /// 是否是自选股
    var isWatchlisted: Bool = false
    /// 最后更新时间
    var lastUpdated: Date?
    /// 关联数据
    @Relationship(deleteRule: .cascade) var priceHistory: [PriceHistory]?
    @Relationship(deleteRule: .cascade) var predictions: [PredictionRecord]?

    init(
        code: String,
        name: String,
        market: String,
        industry: String? = nil,
        listDate: Date? = nil
    ) {
        self.code = code
        self.name = name
        self.market = market
        self.industry = industry
        self.listDate = listDate
        self.lastUpdated = Date()
    }

    /// 中文市场简称
    var marketShort: String {
        if code.hasSuffix(".SH") { return "沪" }
        if code.hasSuffix(".SZ") { return "深" }
        if code.hasPrefix("688") { return "科创" }
        if code.hasPrefix("300") || code.hasPrefix("301") { return "创业" }
        return market
    }

    /// 纯数字代码
    var symbol: String {
        code.replacingOccurrences(of: ".SH", with: "")
            .replacingOccurrences(of: ".SZ", with: "")
    }
}

/// K线日数据
@Model
final class PriceHistory {
    var date: Date
    var open: Double
    var high: Double
    var low: Double
    var close: Double
    var volume: Double
    var amount: Double?
    var turnoverRate: Double?
    var pctChange: Double?
    var stock: StockItem?

    init(
        date: Date,
        open: Double,
        high: Double,
        low: Double,
        close: Double,
        volume: Double,
        amount: Double? = nil,
        turnoverRate: Double? = nil,
        pctChange: Double? = nil
    ) {
        self.date = date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.amount = amount
        self.turnoverRate = turnoverRate
        self.pctChange = pctChange
    }
}

/// AI预测记录
@Model
final class PredictionRecord {
    /// 预测基准日
    var baseDate: Date
    /// 预测目标日 (T+3)
    var targetDate: Date
    /// 预测方向: "up" / "flat" / "down"
    var direction: String
    /// 置信度 0.0~1.0
    var confidence: Double
    /// 预测收益率
    var predictedReturn: Double?
    /// 模型版本
    var modelVersion: String
    /// 实际方向（事后回填，用于评估准确率）
    var actualDirection: String?
    /// 信号标签: "资金流入"/"政策催化"/"技术突破"/"情绪反转"
    var signalTags: [String]?
    /// 关联股票
    var stock: StockItem?

    init(
        baseDate: Date,
        targetDate: Date,
        direction: String,
        confidence: Double,
        modelVersion: String,
        stock: StockItem? = nil
    ) {
        self.baseDate = baseDate
        self.targetDate = targetDate
        self.direction = direction
        self.confidence = confidence
        self.modelVersion = modelVersion
        self.stock = stock
    }

    /// 方向显示
    var directionText: String {
        switch direction {
        case "up": "看涨"
        case "down": "看跌"
        default: "观望"
        }
    }

    var directionColor: String {
        switch direction {
        case "up": return "red"
        case "down": return "green"
        default: return "gray"
        }
    }
}

/// 自选股
@Model
final class WatchlistItem {
    var order: Int = 0
    var addedAt: Date = Date()
    var notes: String?
    var stock: StockItem?

    init(order: Int = 0, stock: StockItem? = nil) {
        self.order = order
        self.stock = stock
    }
}
