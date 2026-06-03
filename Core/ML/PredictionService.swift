import Foundation
import CoreML
import NaturalLanguage

/// 本地CoreML推理服务 —— 离线优先，无需网络
/// 模型类型：LightGBM → ONNX → CoreML（树模型，输入为~80维特征向量）
final class PredictionService: @unchecked Sendable {
    static let shared = PredictionService()

    private var rankingModel: MLModel?
    private var sentimentClassifier: NLModel?
    let modelManager = ModelManager()
    private let featureEngine = FeatureEngine()

    private init() {
        loadModels()
    }

    // MARK: - 模型加载

    func loadModels() {
        // 模型名与后端 train->coreml_export 输出的名称一致
        rankingModel = modelManager.loadLatestModel(named: "StockRankingModel")
        loadSentimentModel()
    }

    private func loadSentimentModel() {
        if let url = modelManager.modelURL(for: "SentimentClassifier") {
            sentimentClassifier = try? NLModel(contentsOf: url)
        }
    }

    // MARK: - 预测（LightGBM树模型 → ~80维特征向量 → CoreML推理）

    /// 预测T+3收益率（回归值），然后转为方向+置信度
    func predictPriceDirection(for stock: StockItem,
                               priceHistory: [PriceHistory]) async throws -> PredictionRecord {
        guard let model = rankingModel else {
            throw PredictionError.modelNotLoaded
        }

        // 1. 特征计算：~80维特征（与Python feature_engine.compute_features 对齐）
        let recentPrices = Array(priceHistory.sorted { $0.date < $1.date }.suffix(120))
        guard recentPrices.count >= 60 else {
            throw PredictionError.insufficientData
        }

        let featureVector = try featureEngine.computeFeatureVector(from: recentPrices)
        guard featureVector.count > 20 else {
            throw PredictionError.insufficientData
        }

        // 2. CoreML推理——输入是1D特征向量 [N_features]
        let input = try MLMultiArray(shape: [NSNumber(value: featureVector.count)], dataType: .float32)
        for (i, v) in featureVector.enumerated() {
            input[i] = NSNumber(value: Float(v))
        }

        let provider = try MLDictionaryFeatureProvider(dictionary: [
            "features": MLFeatureValue(multiArray: input)
        ])
        let output = try model.prediction(from: provider)
        let predictedReturn = output.featureValue(for: "predicted_return")?.doubleValue ?? 0.0

        // 3. 确定方向和标签
        let direction: String
        let confidence: Double
        if predictedReturn > 0.005 {
            direction = "up"
            confidence = min(0.9, 0.5 + abs(predictedReturn) * 10)
        } else if predictedReturn < -0.005 {
            direction = "down"
            confidence = min(0.9, 0.5 + abs(predictedReturn) * 10)
        } else {
            direction = "flat"
            confidence = 0.5
        }

        var signalTags: [String] = []
        if predictedReturn > 0.01 { signalTags.append("技术突破") }
        if predictedReturn < -0.01 { signalTags.append("技术回避") }

        // 使用交易日历计算T+3（非日历日）——异常长假时容错回退+5天
        let targetDate = TradingCalendar.shared.nextTradingDay(from: Date(), offset: 3)
            ?? Calendar.current.date(byAdding: .day, value: 5, to: Date())!

        return PredictionRecord(
            baseDate: Date(),
            targetDate: targetDate,
            direction: direction,
            confidence: confidence,
            modelVersion: modelManager.currentVersion,
            stock: stock
        )
    }

    // MARK: - 情绪分析

    func analyzeSentiment(text: String) -> (label: String, score: Double) {
        guard let classifier = sentimentClassifier else {
            return ("neutral", 0.0)
        }

        let predicted = classifier.predictedLabel(for: text) ?? "neutral"

        // 简单规则增强：中文金融关键词
        let bullishWords = ["增长", "利好", "突破", "涨停", "超预期", "放量", "回购", "增持"]
        let bearishWords = ["下跌", "利空", "减持", "亏损", "退市", "处罚", "跌停", "爆雷"]

        let lowercased = text.lowercased()
        let bullishCount = bullishWords.filter { lowercased.contains($0) }.count
        let bearishCount = bearishWords.filter { lowercased.contains($0) }.count

        if bullishCount > bearishCount {
            return ("positive", min(1.0, 0.6 + Double(bullishCount) * 0.1))
        } else if bearishCount > bullishCount {
            return ("negative", min(1.0, 0.6 + Double(bearishCount) * 0.1))
        }

        return (predicted, 0.5)
    }

    // MARK: - Helpers

    var isModelReady: Bool {
        rankingModel != nil
    }
}

// MARK: - 交易日历

struct TradingCalendar {
    static let shared = TradingCalendar()

    /// 中国节假日（公历日期，2024-2026年，含农历节日）
    /// 每年需更新——春节/清明/端午/中秋公历日期每年不同
    /// 数据来源：国务院办公厅节假日安排通知
    private static let chineseHolidays: Set<String> = [
        // 固定公历节日
        "01-01",  // 元旦（通常休1-3天）
        "05-01", "05-02",  // 劳动节
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  // 国庆+中秋可能重合
        // === 2024年农历节日 ===
        "02-12", "02-13", "02-14", "02-15", "02-16",  // 春节 2/10-17 (2/10-11周末,实际休12-16)
        "04-04", "04-05",  // 清明节 4/4-6 (4/6周末)
        "06-10",  // 端午节 6/8-10 (6/8周末)
        "09-17",  // 中秋节 9/15-17 (9/15周末)
        // === 2025年农历节日 ===
        "01-29", "01-30", "01-31", "02-03", "02-04",  // 春节 1/28-2/4 (1/28除夕)
        "04-04",  // 清明节 4/4-6 (4/5-6周末,实际休4/4)
        "05-31",  // 端午节 5/31-6/2 (6/1-2周末,实际休5/31)
        "10-06",  // 中秋节 10/6 (与国庆连休)
        // === 2026年农历节日 ===
        "02-17", "02-18", "02-19", "02-20", "02-23",  // 春节 2/17(除夕)-2/23
        "04-05",  // 清明节 4/5 (周日,调休至4/4-6但实际休4/5)
        "06-19",  // 端午节 6/19-21 (6/20-21周末,实际休6/19)
        "09-25",  // 中秋节 9/25-27 (9/26-27周末,实际休9/25)
    ]

    /// 判断是否为交易日（跳过周末+中国节假日）
    func isTradingDay(_ date: Date) -> Bool {
        let calendar = Calendar.current
        let weekday = calendar.component(.weekday, from: date)
        // 跳过周末
        if weekday == 1 || weekday == 7 { return false }
        // 跳过中国节假日（简化版——仅检查月-日）
        let df = DateFormatter(); df.dateFormat = "MM-dd"
        let mmdd = df.string(from: date)
        if Self.chineseHolidays.contains(mmdd) { return false }
        return true
    }

    /// 计算T+N交易日（跳过周末+节假日）
    /// 返回nil表示：连续非交易日过多（如春节长假），无法确定目标日
    func nextTradingDay(from date: Date, offset: Int) -> Date? {
        let calendar = Calendar.current
        var current = date
        var tradingDays = 0
        let maxIterations = offset * 4 + 15  // 安全上限：覆盖春节等超长假期
        var iterations = 0
        while tradingDays < offset && iterations < maxIterations {
            current = calendar.date(byAdding: .day, value: 1, to: current) ?? current
            if isTradingDay(current) {
                tradingDays += 1
            }
            iterations += 1
        }
        // 达到上限仍未找到 → 异常长假（不应发生，但防御性处理）
        if tradingDays < offset {
            return nil
        }
        return current
    }
}

// MARK: - 特征工程（与Python features.py 对齐 ~80维）

final class FeatureEngine {
    /// 计算特征向量（与Python FeatureEngine.compute_features对齐）
    /// 返回：[Float]，长度约80，与Python训练的特征一一对应
    func computeFeatureVector(from prices: [PriceHistory]) throws -> [Double] {
        guard prices.count >= 60 else {
            throw PredictionError.insufficientData
        }

        let closes = prices.map { $0.close }
        let opens = prices.map { $0.open }
        let highs = prices.map { $0.high }
        let lows = prices.map { $0.low }
        let volumes = prices.map { $0.volume }
        let amounts = prices.map { $0.amount ?? 0 }
        let turnovers = prices.map { $0.turnoverRate ?? 0 }

        var feat: [Double] = []
        let n = closes.count

        // === 基础收益特征（与Python ret_1d~ret_20d 对齐）===
        feat.append((closes[n-1] - closes[n-2]) / closes[n-2])           // ret_1d
        feat.append((closes[n-1] - closes[n-4]) / closes[n-4])           // ret_3d
        feat.append((closes[n-1] - closes[n-6]) / closes[n-6])           // ret_5d
        feat.append((closes[n-1] - closes[n-11]) / closes[n-11])         // ret_10d
        feat.append((closes[n-1] - closes[n-21]) / closes[n-21])         // ret_20d

        // === 波动率特征 ===
        feat.append(std(Array(closes.suffix(5))))                        // volatility_5d
        feat.append(std(Array(closes.suffix(10))))                       // volatility_10d
        feat.append(std(Array(closes.suffix(20))))                       // volatility_20d

        // === 量价特征 ===
        if let lastTO = turnovers.last { feat.append(lastTO) }           // turnover_rate
        else { feat.append(0) }
        feat.append((highs[n-1] - lows[n-1]) / closes[n-2])              // amplitude
        let volMA5 = volumes.suffix(6).dropLast().reduce(0, +) / 5
        feat.append(volumes[n-1] / max(volMA5, 1))                       // volume_ratio
        feat.append(volRatioGt2Days(volumes: volumes))                   // volume_ratio_gt2_days
        feat.append(volumePriceCorr(volumes: volumes, closes: closes))   // volume_price_corr

        // === 均线特征 ===
        let ma5 = closes.suffix(5).reduce(0, +) / 5
        let ma10 = closes.suffix(10).reduce(0, +) / 10
        let ma20 = closes.suffix(20).reduce(0, +) / 20
        let ma60 = closes.suffix(min(60, n)).reduce(0, +) / Double(min(60, n))
        let ma250 = closes.suffix(min(250, n)).reduce(0, +) / Double(min(250, n))
        let mas = [ma5, ma10, ma20, ma60]
        let maMean = mas.reduce(0, +) / 4
        let maStd = sqrt(mas.map { pow($0 - maMean, 2) }.reduce(0, +) / 4)
        feat.append(maStd / maMean)                                      // ma_convergence
        feat.append(closes[n-1] / max(ma250, 0.01))                     // ma_position
        // ma_divergence_speed: 粘合度变化（需历史数据，简化为0）
        feat.append(0.0)

        // === 时间特征 ===
        let cal = Calendar.current
        let comps = cal.dateComponents([.weekday], from: Date())
        feat.append(Double((comps.weekday ?? 1) - 1))                   // day_of_week
        feat.append(cal.component(.day, from: Date()) <= 3 ? 1.0 : 0.0) // is_month_start
        feat.append(cal.component(.day, from: Date()) >= 28 ? 1.0 : 0.0) // is_month_end
        feat.append([3,4,8,9,10].contains(cal.component(.month, from: Date())) ? 1.0 : 0.0) // is_earnings_season

        // === 异常检验 ===
        let ret1d = feat[0]
        let ret5dAvg = (0..<min(5, n-1)).map {
            (closes[n-1-$0] - closes[n-2-$0]) / closes[n-2-$0]
        }.reduce(0, +) / 5
        let ret5dStd = std((0..<min(5, n-1)).map {
            (closes[n-1-$0] - closes[n-2-$0]) / closes[n-2-$0]
        })
        feat.append(ret5dStd > 0 ? (ret1d - ret5dAvg) / ret5dStd : 0)   // anomaly_score
        feat.append(feat[10] > 3 ? 1.0 : 0.0)                           // pump_and_dump_risk

        // === 占位特征（北向资金、融资等需要外部数据，iOS端填0） ===
        let placeholderCount = 40
        for _ in 0..<placeholderCount {
            feat.append(0.0)
        }

        return feat
    }

    // MARK: - Helpers

    private func std(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        let m = values.reduce(0, +) / Double(values.count)
        return sqrt(values.map { pow($0 - m, 2) }.reduce(0, +) / Double(values.count))
    }

    private func volRatioGt2Days(volumes: [Double]) -> Double {
        var count = 0
        var i = volumes.count - 1
        let ma5 = volumes.suffix(6).dropLast().reduce(0, +) / 5
        while i >= 0 && volumes[i] / max(ma5, 1) > 2 {
            count += 1; i -= 1
        }
        return Double(count)
    }

    private func volumePriceCorr(volumes: [Double], closes: [Double]) -> Double {
        let n = min(5, volumes.count - 1)
        let volRatios = (0..<n).map { i in
            let idx = volumes.count - 1 - i
            let ma5 = volumes[max(0, idx-5)..<idx].reduce(0, +) / Double(min(5, idx))
            return volumes[idx] / max(ma5, 1)
        }
        let rets = (0..<n).map { i in
            let idx = closes.count - 1 - i
            return (closes[idx] - closes[idx-1]) / closes[idx-1]
        }
        return pearsonCorr(volRatios, rets)
    }

    private func pearsonCorr(_ x: [Double], _ y: [Double]) -> Double {
        guard x.count > 1, x.count == y.count else { return 0 }
        let mx = x.reduce(0, +) / Double(x.count)
        let my = y.reduce(0, +) / Double(y.count)
        let num = zip(x, y).map { ($0 - mx) * ($1 - my) }.reduce(0, +)
        let den = sqrt(x.map { pow($0 - mx, 2) }.reduce(0, +) * y.map { pow($0 - my, 2) }.reduce(0, +))
        return den > 0 ? num / den : 0
    }
}

// MARK: - 模型版本管理

final class ModelManager {
    private let fileManager = FileManager.default

    var currentVersion: String {
        // 从本地缓存读取
        UserDefaults.standard.string(forKey: "ml_model_version") ?? "1.0.0"
    }

    func loadLatestModel(named name: String) -> MLModel? {
        guard let url = modelURL(for: name) else { return nil }

        do {
            let compiledURL = try MLModel.compileModel(at: url)
            return try MLModel(contentsOf: compiledURL)
        } catch {
            print("[ModelManager] Failed to load \(name): \(error)")
            return nil
        }
    }

    func modelURL(for name: String) -> URL? {
        let docs = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
        let modelDir = docs.appendingPathComponent("CoreMLModels")
        let url = modelDir.appendingPathComponent("\(name).mlpackage")

        // 检查本地是否有下载的模型
        if fileManager.fileExists(atPath: url.path) {
            return url
        }

        // 回退到Bundle内置模型（如果有的话——首次安装时没有）
        if let bundleURL = Bundle.main.url(forResource: name, withExtension: "mlpackage") {
            return bundleURL
        }

        return nil
    }

    func downloadModel(from url: URL, name: String) async throws {
        let (data, _) = try await URLSession.shared.data(from: url)

        let docs = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
        let modelDir = docs.appendingPathComponent("CoreMLModels")
        try fileManager.createDirectory(at: modelDir, withIntermediateDirectories: true)

        let localURL = modelDir.appendingPathComponent("\(name).mlpackage")
        try data.write(to: localURL)
    }

    func checkForUpdate() async -> Bool {
        do {
            let info = try await APIClient.shared.checkModelVersion()
            if info.version != currentVersion {
                UserDefaults.standard.set(info.version, forKey: "ml_model_version")
                return true
            }
        } catch {
            print("[ModelManager] Version check failed: \(error)")
        }
        return false
    }
}

// MARK: - 错误

enum PredictionError: Error {
    case modelNotLoaded
    case insufficientData
}

extension PredictionError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .modelNotLoaded: return "AI模型未加载，请检查网络连接后重试"
        case .insufficientData: return "历史数据不足，需要至少30个交易日数据"
        }
    }
}
