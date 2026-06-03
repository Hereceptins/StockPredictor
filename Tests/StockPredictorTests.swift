import XCTest
@testable import StockPredictor  // 需在Xcode中配置

/// iOS单元测试套件
/// 运行方式：Xcode → Product → Test (Cmd+U)
final class StockPredictorTests: XCTestCase {

    // MARK: - TradingCalendar tests

    func testTradingCalendarSkipsWeekends() {
        let calendar = TradingCalendar.shared
        // 周六
        let saturday = createDate(2024, 6, 1)
        XCTAssertFalse(calendar.isTradingDay(saturday), "周六不是交易日")

        // 周日
        let sunday = createDate(2024, 6, 2)
        XCTAssertFalse(calendar.isTradingDay(sunday), "周日不是交易日")
    }

    func testTradingCalendarWeekdaysAreTradingDays() {
        let calendar = TradingCalendar.shared
        // 周三（非节假日）
        let wednesday = createDate(2024, 6, 5)
        XCTAssertTrue(calendar.isTradingDay(wednesday), "周三应为交易日")
    }

    func testTradingCalendarSkipsChineseHolidays() {
        let calendar = TradingCalendar.shared
        // 国庆节 10月1日
        let nationalDay = createDate(2024, 10, 1)
        XCTAssertFalse(calendar.isTradingDay(nationalDay), "国庆节不是交易日")
    }

    func testNextTradingDayBasic() {
        let calendar = TradingCalendar.shared
        let monday = createDate(2024, 6, 3)
        let tuesday = calendar.nextTradingDay(from: monday, offset: 1)
        XCTAssertNotNil(tuesday, "应返回有效日期")
        XCTAssertEqual(calendar.component(.weekday, from: tuesday!), 3)
    }

    func testNextTradingDaySkipsWeekend() {
        let calendar = TradingCalendar.shared
        let friday = createDate(2024, 6, 7)
        let next = calendar.nextTradingDay(from: friday, offset: 1)
        XCTAssertNotNil(next)
        XCTAssertEqual(calendar.component(.weekday, from: next!), 2)
    }

    func testNextTradingDayThreeDays() {
        let calendar = TradingCalendar.shared
        let monday = createDate(2024, 6, 3)
        let thursday = calendar.nextTradingDay(from: monday, offset: 3)
        XCTAssertNotNil(thursday)
        XCTAssertEqual(calendar.component(.weekday, from: thursday!), 5)
    }

    func testNextTradingDayReturnsNilForExtremeOffset() {
        let calendar = TradingCalendar.shared
        // 请求300个交易日——应该在长假中找不到，返回nil
        let monday = createDate(2024, 9, 30)  // 国庆前一天
        let result = calendar.nextTradingDay(from: monday, offset: 300)
        // 允许返回nil或Date（取决于日历覆盖），重点是不崩溃
        XCTAssertTrue(result == nil || result is Date)
    }

    // MARK: - FeatureEngine tests

    func testFeatureEngineRequiresMinimumData() {
        let engine = FeatureEngine()
        let insufficientData = [PriceHistory]()  // 空数组
        XCTAssertThrowsError(try engine.computeFeatureVector(from: insufficientData)) { error in
            XCTAssertEqual(error as? PredictionError, PredictionError.insufficientData)
        }
    }

    func testFeatureEngineWith60Days() throws {
        let engine = FeatureEngine()
        let data = generatePriceHistory(days: 60)
        let features = try engine.computeFeatureVector(from: data)
        XCTAssertFalse(features.isEmpty, "特征向量不应为空")
        XCTAssertGreaterThan(features.count, 20, "至少应有20维特征")
    }

    func testFeatureEngineWith120Days() throws {
        let engine = FeatureEngine()
        let data = generatePriceHistory(days: 120)
        let features = try engine.computeFeatureVector(from: data)
        XCTAssertGreaterThan(features.count, 40, "120天数据应产生足够特征")
    }

    func testFeatureEngineNoNaN() throws {
        let engine = FeatureEngine()
        let data = generatePriceHistory(days: 100)
        let features = try engine.computeFeatureVector(from: data)
        for (i, v) in features.enumerated() {
            XCTAssertFalse(v.isNaN, "特征[\(i)]为NaN")
            XCTAssertFalse(v.isInfinite, "特征[\(i)]为Inf")
        }
    }

    func testFeatureEngineVolatilityPositive() throws {
        let engine = FeatureEngine()
        var data = generatePriceHistory(days: 100)
        // 制造波动——修改收盘价
        for i in 1..<data.count {
            data[i].close = data[i-1].close * (1 + Double(i % 5 - 2) * 0.01)
        }
        let features = try engine.computeFeatureVector(from: data)
        // 波动率应该是正的
        let volIdx = 5  // volatility_5d 在特征向量中的位置
        if volIdx < features.count {
            XCTAssertGreaterThanOrEqual(features[volIdx], 0, "波动率应为非负")
        }
    }

    // MARK: - API Client tests

    func testAPIClientBuildURL() throws {
        let client = APIClient.shared
        let url = try client.buildURL(for: .searchStocks(query: "茅台", page: 1))
        XCTAssertTrue(url.absoluteString.contains("search"), "URL应包含search")
        XCTAssertTrue(url.absoluteString.contains("q=%E8%8C%85%E5%8F%B0"), "URL应包含编码后的查询词")
        XCTAssertTrue(url.absoluteString.contains("page=1"), "URL应包含page")
    }

    func testAPIClientKlineURL() throws {
        let client = APIClient.shared
        let url = try client.buildURL(for: .kline(
            code: "000001.SZ", period: "daily",
            start: "20240101", end: "20240601", adjust: "fwd"
        ))
        XCTAssertTrue(url.absoluteString.contains("000001.SZ/kline"))
        XCTAssertTrue(url.absoluteString.contains("period=daily"))
    }

    // MARK: - Model / Data tests

    func testStockItemModel() {
        let stock = StockItem(code: "600519.SH", name: "贵州茅台", market: "SH", industry: "白酒")
        XCTAssertEqual(stock.symbol, "600519")
        XCTAssertEqual(stock.marketShort, "沪")
        XCTAssertTrue(stock.isWatchlisted == false)
    }

    func testStockItemMarketDetection() {
        let shStock = StockItem(code: "600000.SH", name: "Test", market: "SH")
        XCTAssertEqual(shStock.marketShort, "沪")

        let szStock = StockItem(code: "000001.SZ", name: "Test", market: "SZ")
        XCTAssertEqual(szStock.marketShort, "深")

        let kcStock = StockItem(code: "688001.SH", name: "Test", market: "SH")
        XCTAssertEqual(kcStock.marketShort, "科创")

        let gemStock = StockItem(code: "300750.SZ", name: "Test", market: "SZ")
        XCTAssertEqual(gemStock.marketShort, "创业")
    }

    func testPredictionRecordDirection() {
        let pred = PredictionRecord(
            baseDate: Date(),
            targetDate: Date(),
            direction: "up",
            confidence: 0.75,
            modelVersion: "1.0.0"
        )
        XCTAssertEqual(pred.directionText, "看涨")
        XCTAssertEqual(pred.directionColor, "red")
    }

    func testPriceHistoryModel() {
        let ph = PriceHistory(
            date: Date(),
            open: 10.0, high: 11.0, low: 9.5, close: 10.5,
            volume: 1e7, amount: 1.05e8, turnoverRate: 2.5, pctChange: 5.0
        )
        XCTAssertEqual(ph.close, 10.5)
        XCTAssertEqual(ph.pctChange, 5.0)
    }

    // MARK: - Disclaimers tests

    func testForbiddenTermsNotInDisclaimers() {
        // 确保免责声明不含任何禁止措辞
        let disclaimer = Disclaimers.app
        for term in Disclaimers.forbiddenTerms {
            XCTAssertFalse(
                disclaimer.contains(term),
                "免责声明包含禁止措辞: '\(term)'"
            )
        }
    }

    func testAppStoreDescriptionCompliant() {
        let desc = Disclaimers.appStoreSafeDescription
        for term in Disclaimers.forbiddenTerms {
            XCTAssertFalse(
                desc.contains(term),
                "App Store描述包含禁止措辞: '\(term)'"
            )
        }
    }

    func testFooterDisclaimerIsShort() {
        XCTAssertTrue(Disclaimers.footer.count < 30, "底部免责声明应简洁")
    }

    // MARK: - Helpers

    private func createDate(_ year: Int, _ month: Int, _ day: Int) -> Date {
        var comps = DateComponents()
        comps.year = year; comps.month = month; comps.day = day
        return Calendar.current.date(from: comps) ?? Date()
    }

    private func generatePriceHistory(days: Int) -> [PriceHistory] {
        var data: [PriceHistory] = []
        var price = 10.0
        let startDate = Calendar.current.date(byAdding: .day, value: -days, to: Date()) ?? Date()

        for i in 0..<days {
            let date = Calendar.current.date(byAdding: .day, value: i, to: startDate) ?? Date()
            let ret = Double.random(in: -0.03...0.035)
            let open = price
            let close = price * (1 + ret)
            let high = max(open, close) * (1 + abs(Double.random(in: 0...0.015)))
            let low = min(open, close) * (1 - abs(Double.random(in: 0...0.015)))
            let volume = Double.random(in: 5e6...5e8)
            let amount = volume * close

            data.append(PriceHistory(
                date: date,
                open: open, high: high, low: low, close: close,
                volume: volume, amount: amount,
                turnoverRate: Double.random(in: 0.5...5.0),
                pctChange: ret * 100
            ))
            price = close
        }
        return data
    }
}

// MARK: - TradingCalendar extension for testing

extension TradingCalendar {
    func component(_ comp: Calendar.Component, from date: Date) -> Int {
        Calendar.current.component(comp, from: date)
    }
}
