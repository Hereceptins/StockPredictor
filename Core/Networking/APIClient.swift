import Foundation

/// API客户端 —— 与Python后端通信
final class APIClient: Sendable {
    static let shared = APIClient()

    private let session: URLSession
    private let baseURL: String
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)

        // 默认后端地址（开发环境）
        baseURL = ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "http://localhost:8000"

        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        encoder = JSONEncoder()
    }

    // MARK: - 通用请求

    // MARK: - URL构建（实例方法，非全局函数）
    func buildURL(for endpoint: APIEndpoint) throws -> URL {
        var components = URLComponents(string: "\(baseURL)\(endpoint.path)")
        let items = endpoint.queryItems
        if !items.isEmpty {
            components?.queryItems = items
        }
        guard let url = components?.url else {
            throw APIError.invalidURL
        }
        return url
    }

    func request<T: Decodable>(_ endpoint: APIEndpoint) async throws -> APIResponse<T> {
        let url = try buildURL(for: endpoint)
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // API Key 认证（与后端 config.py api_key_header 一致）
        if let apiKey = ProcessInfo.processInfo.environment["API_KEY"] {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }

        if let body = endpoint.body {
            request.httpBody = try encoder.encode(body)
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError(httpResponse.statusCode)
        }

        return try decoder.decode(APIResponse<T>.self, from: data)
    }

    // MARK: - 股票API

    func searchStocks(query: String, page: Int = 1) async throws -> [StockSearchResult] {
        let endpoint = APIEndpoint.searchStocks(query: query, page: page)
        let response: APIResponse<[StockSearchResult]> = try await request(endpoint)
        return response.data
    }

    func fetchKLine(code: String, period: String = "daily",
                     start: String, end: String, adjust: String = "fwd") async throws -> [KLineData] {
        let endpoint = APIEndpoint.kline(code: code, period: period, start: start, end: end, adjust: adjust)
        let response: APIResponse<[KLineData]> = try await request(endpoint)
        return response.data
    }

    func fetchPrediction(code: String, days: Int = 5) async throws -> PredictionData {
        let endpoint = APIEndpoint.prediction(code: code, days: days)
        let response: APIResponse<PredictionData> = try await request(endpoint)
        return response.data
    }

    func fetchDailyPool() async throws -> [PoolStock] {
        let endpoint = APIEndpoint.dailyPool
        let response: APIResponse<[PoolStock]> = try await request(endpoint)
        return response.data
    }

    func fetchSentiment(code: String, page: Int = 1) async throws -> [SentimentItem] {
        let endpoint = APIEndpoint.sentiment(code: code, page: page)
        let response: APIResponse<[SentimentItem]> = try await request(endpoint)
        return response.data
    }

    func checkModelVersion() async throws -> ModelVersionInfo {
        let endpoint = APIEndpoint.modelVersion
        let response: APIResponse<ModelVersionInfo> = try await request(endpoint)
        return response.data
    }
}

// MARK: - API端点定义

enum APIEndpoint {
    case searchStocks(query: String, page: Int)
    case kline(code: String, period: String, start: String, end: String, adjust: String)
    case prediction(code: String, days: Int)
    case dailyPool
    case sentiment(code: String, page: Int)
    case modelVersion
    case limitUpDown(date: String)
    case dragonTiger(date: String)

    var path: String {
        switch self {
        case .searchStocks: return "/api/v1/stocks/search"
        case .kline(let code, _, _, _, _): return "/api/v1/stocks/\(code)/kline"
        case .prediction(let code, _): return "/api/v1/predictions/\(code)"
        case .dailyPool: return "/api/v1/predictions/daily-pool"
        case .sentiment(let code, _): return "/api/v1/sentiment/\(code)"
        case .modelVersion: return "/api/v1/models/latest-version"
        case .limitUpDown: return "/api/v1/board/limit-up-down"
        case .dragonTiger: return "/api/v1/board/dragon-tiger"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .searchStocks, .kline, .prediction, .dailyPool, .sentiment,
             .modelVersion, .limitUpDown, .dragonTiger:
            return .get
        }
    }

    var queryItems: [URLQueryItem] {
        switch self {
        case .searchStocks(let q, let p):
            return [URLQueryItem(name: "q", value: q),
                    URLQueryItem(name: "page", value: String(p)),
                    URLQueryItem(name: "size", value: "20")]
        case .kline(_, let period, let start, let end, let adjust):
            return [URLQueryItem(name: "period", value: period),
                    URLQueryItem(name: "start", value: start),
                    URLQueryItem(name: "end", value: end),
                    URLQueryItem(name: "adjust", value: adjust)]
        case .prediction(_, let days):
            return [URLQueryItem(name: "days", value: String(days))]
        case .sentiment(_, let page):
            return [URLQueryItem(name: "page", value: String(page))]
        case .limitUpDown(let date):
            return [URLQueryItem(name: "date", value: date)]
        case .dragonTiger(let date):
            return [URLQueryItem(name: "date", value: date)]
        default: return []
        }
    }

    var body: (any Encodable)? { nil }
}

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
}

// MARK: - 响应模型

struct APIResponse<T: Decodable>: Decodable {
    let code: Int
    let message: String
    let data: T
    let disclaimer: String?
}

// MARK: - 数据模型

struct StockSearchResult: Decodable {
    let code: String
    let name: String
    let market: String
    let industry: String?
}

struct KLineData: Decodable {
    let date: String
    let open: Double
    let high: Double
    let low: Double
    let close: Double
    let volume: Double
    let amount: Double?
    let turnoverRate: Double?
    let pctChange: Double?
}

struct PredictionData: Decodable {
    let direction: String
    let confidence: Double
    let predictedReturn: Double?
    let signalTags: [String]?
    let modelVersion: String
}

struct PoolStock: Decodable {
    let code: String
    let name: String
    let direction: String
    let confidence: Double
    let signalTags: [String]?
    let overallScore: Double?
}

struct SentimentItem: Decodable {
    let title: String
    let source: String
    let sentiment: String
    let publishedAt: String
}

struct ModelVersionInfo: Decodable {
    let version: String
    let accuracy: Double?
    let downloadURL: String?
}

// MARK: - 错误

enum APIError: Error {
    case invalidURL
    case invalidResponse
    case httpError(Int)
    case decodingError(Error)
    case networkError(Error)
}
