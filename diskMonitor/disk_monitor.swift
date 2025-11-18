#!/usr/bin/env swift

import Foundation

// Global flag for signal handling (safe to use in signal handlers)
var globalShouldStop = false

struct DiskInfo {
    let totalGB: Double
    let usedGB: Double
    let freeGB: Double
    let percentUsed: Double
    let mountPoint: String
}

struct Config {
    let pushoverToken: String
    let pushoverUserKey: String
    let thresholdPercent: Double
    let checkIntervalSeconds: Int
    let mountPoint: String
    let alertCooldownMinutes: Int
    let pushoverPriority: Int
    let pushoverSound: String
    let machineName: String
    let pushoverRetry: Int  // Retry interval in seconds (required for priority 2)
    let pushoverExpire: Int // Expire time in seconds (required for priority 2)
    
    static func load(from path: String) throws -> Config {
        let url = URL(fileURLWithPath: path)
        let data = try Data(contentsOf: url)
        let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        
        guard let token = json["pushover_token"] as? String,
              let userKey = json["pushover_user_key"] as? String else {
            throw NSError(domain: "ConfigError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Missing required config fields: pushover_token, pushover_user_key"])
        }
        
        // Auto-detect machine name if not provided in config
        let machineName: String
        if let configMachineName = json["machine_name"] as? String, !configMachineName.isEmpty {
            machineName = configMachineName
        } else {
            // Try to get the computer name from the system
            if let hostName = Host.current().localizedName {
                machineName = hostName
            } else {
                machineName = Host.current().name ?? "Unknown"
            }
        }
        
        return Config(
            pushoverToken: token,
            pushoverUserKey: userKey,
            thresholdPercent: (json["threshold_percent"] as? Double) ?? 90.0,
            checkIntervalSeconds: (json["check_interval_seconds"] as? Int) ?? 60,
            mountPoint: (json["mount_point"] as? String) ?? "/",
            alertCooldownMinutes: (json["alert_cooldown_minutes"] as? Int) ?? 60,
            pushoverPriority: (json["pushover_priority"] as? Int) ?? 1,
            pushoverSound: (json["pushover_sound"] as? String) ?? "pushover",
            machineName: machineName,
            pushoverRetry: (json["pushover_retry"] as? Int) ?? 30,
            pushoverExpire: (json["pushover_expire"] as? Int) ?? 59
        )
    }
    
    static func createExample(at path: String) {
        // Auto-detect machine name for example config
        let machineName: String
        if let hostName = Host.current().localizedName {
            machineName = hostName
        } else {
            machineName = Host.current().name ?? "YOUR_MACHINE_NAME"
        }
        
        let example: [String: Any] = [
            "pushover_token": "YOUR_APP_TOKEN_HERE",
            "pushover_user_key": "YOUR_USER_KEY_HERE",
            "threshold_percent": 90,
            "check_interval_seconds": 60,
            "mount_point": "/",
            "alert_cooldown_minutes": 60,
            "pushover_priority": 1,
            "pushover_sound": "pushover",
            "machine_name": machineName,
            "pushover_retry": 30,
            "pushover_expire": 59
        ]
        
        let url = URL(fileURLWithPath: path)
        let data = try! JSONSerialization.data(withJSONObject: example, options: [.prettyPrinted])
        try! data.write(to: url)
        print("Created example config at: \(path)")
        print("Please edit it with your Pushover credentials.")
    }
}

class DiskMonitor {
    let config: Config
    var alertSent = false
    var lastCheckTime: Date?
    
    init(configPath: String = "config.json") throws {
        do {
            self.config = try Config.load(from: configPath)
        } catch {
            if (error as NSError).code == NSFileReadNoSuchFileError {
                print("Error: Config file '\(configPath)' not found.")
                print("Creating example config file...")
                Config.createExample(at: configPath)
            }
            throw error
        }
    }
    
    func getDiskUsage() -> DiskInfo? {
        let fileURL = URL(fileURLWithPath: config.mountPoint)
        
        do {
            let resourceValues = try fileURL.resourceValues(forKeys: [
                .volumeTotalCapacityKey,
                .volumeAvailableCapacityForImportantUsageKey
            ])
            
            guard let totalCapacity = resourceValues.volumeTotalCapacity,
                  let availableCapacity = resourceValues.volumeAvailableCapacityForImportantUsage else {
                print("Error: Failed to retrieve disk space information")
                return nil
            }
            
            // Convert to Int64 for calculation
            let totalBytes = Int64(totalCapacity)
            let availableBytes = Int64(availableCapacity)
            let usedBytes = totalBytes - availableBytes
            
            // Convert to GB (decimal, 1000^3 to match macOS display)
            let totalGB = Double(totalBytes) / 1_000_000_000
            let availableGB = Double(availableBytes) / 1_000_000_000
            let usedGB = Double(usedBytes) / 1_000_000_000
            let percentUsed = (Double(usedBytes) / Double(totalBytes)) * 100.0
            
            return DiskInfo(
                totalGB: totalGB,
                usedGB: usedGB,
                freeGB: availableGB,
                percentUsed: percentUsed,
                mountPoint: config.mountPoint
            )
        } catch {
            print("Error retrieving disk space: \(error.localizedDescription)")
            return nil
        }
    }
    
    func sendPushoverNotification(diskInfo: DiskInfo) -> Bool {
        let url = URL(string: "https://api.pushover.net/1/messages.json")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        
        let message = String(format: "⚠️ Disk Space Alert!\n\nMachine: %@\nMount Point: %@\nUsage: %.1f%%\nUsed: %.1f GB\nFree: %.1f GB\nTotal: %.1f GB",
                           config.machineName,
                           diskInfo.mountPoint,
                           diskInfo.percentUsed,
                           diskInfo.usedGB,
                           diskInfo.freeGB,
                           diskInfo.totalGB)
        
        // Build form-encoded body manually to match Pushover API requirements
        // According to https://pushover.net/api, parameters should be percent-encoded
        // Use a character set that allows alphanumerics and common safe characters
        let allowedChars = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        func formEncode(_ value: String) -> String {
            return value.addingPercentEncoding(withAllowedCharacters: allowedChars) ?? value
        }
        
        // Build form data array
        var formDataArray = [
            "token=\(formEncode(config.pushoverToken))",
            "user=\(formEncode(config.pushoverUserKey))",
            "message=\(formEncode(message))",
            "title=\(formEncode("Disk Space Warning"))",
            "priority=\(formEncode(String(config.pushoverPriority)))",
            "sound=\(formEncode(config.pushoverSound))"
        ]
        
        // Add retry and expire parameters if priority is 2 (emergency)
        if config.pushoverPriority == 2 {
            formDataArray.append("retry=\(config.pushoverRetry)")
            formDataArray.append("expire=\(config.pushoverExpire)")
        }
        
        let formData = formDataArray.joined(separator: "&")
        
        request.httpBody = formData.data(using: .utf8)
        
        let semaphore = DispatchSemaphore(value: 0)
        var success = false
        
        let task = URLSession.shared.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            
            if let error = error {
                print("✗ Error sending notification: \(error.localizedDescription)")
                return
            }
            
            guard let httpResponse = response as? HTTPURLResponse else {
                print("✗ Error: Invalid response")
                return
            }
            
            if let data = data {
                if httpResponse.statusCode == 200 {
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let status = json["status"] as? Int, status == 1 {
                        print("✓ Pushover notification sent successfully")
                        success = true
                    } else {
                        let responseText = String(data: data, encoding: .utf8) ?? "Unknown error"
                        print("✗ Pushover notification failed: \(responseText)")
                    }
                } else {
                    // 4xx errors - show the error details from Pushover
                    let responseText = String(data: data, encoding: .utf8) ?? "Unknown error"
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let errors = json["errors"] as? [String] {
                        print("✗ Error sending notification: HTTP \(httpResponse.statusCode)")
                        print("  Pushover errors: \(errors.joined(separator: ", "))")
                    } else {
                        print("✗ Error sending notification: HTTP \(httpResponse.statusCode)")
                        print("  Response: \(responseText)")
                    }
                }
            } else {
                print("✗ Error sending notification: HTTP \(httpResponse.statusCode) (no response body)")
            }
        }
        
        task.resume()
        semaphore.wait()
        
        return success
    }
    
    func shouldSendAlert() -> Bool {
        if !alertSent {
            return true
        }
        
        guard let lastCheck = lastCheckTime else {
            return true
        }
        
        let elapsedMinutes = Date().timeIntervalSince(lastCheck) / 60.0
        return elapsedMinutes >= Double(config.alertCooldownMinutes)
    }
    
    func checkDiskSpace() {
        guard let diskInfo = getDiskUsage() else {
            return
        }
        
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let timestamp = formatter.string(from: Date())
        let status = String(format: "[%@] %@: %.1f%% used", timestamp, diskInfo.mountPoint, diskInfo.percentUsed)
        
        if diskInfo.percentUsed >= config.thresholdPercent {
            print("\(status) ⚠️  THRESHOLD EXCEEDED")
            
            if shouldSendAlert() {
                print("Sending alert...")
                if sendPushoverNotification(diskInfo: diskInfo) {
                    alertSent = true
                    lastCheckTime = Date()
                }
            } else if let lastCheck = lastCheckTime {
                print("Alert cooldown active (last sent: \(formatter.string(from: lastCheck)))")
            }
        } else {
            print("\(status) ✓")
            if alertSent {
                print("Usage below threshold - resetting alert flag")
                alertSent = false
            }
        }
    }
    
    func run() {
        print(String(repeating: "=", count: 60))
        print("Disk Space Monitor Starting")
        print(String(repeating: "=", count: 60))
        print("Mount Point: \(config.mountPoint)")
        print("Threshold: \(Int(config.thresholdPercent))%")
        print("Check Interval: \(config.checkIntervalSeconds) seconds")
        print("Alert Cooldown: \(config.alertCooldownMinutes) minutes")
        print(String(repeating: "=", count: 60))
        print()
        
        // Set up signal handler for Ctrl-C (SIGINT)
        signal(SIGINT) { _ in
            globalShouldStop = true
        }
        
        // Reset the global flag
        globalShouldStop = false
        
        while !globalShouldStop {
            checkDiskSpace()
            
            // Use a loop with smaller sleep intervals to check shouldStop more frequently
            let sleepInterval = 0.1
            let totalSleep = Double(config.checkIntervalSeconds)
            var slept = 0.0
            
            while slept < totalSleep && !globalShouldStop {
                Thread.sleep(forTimeInterval: sleepInterval)
                slept += sleepInterval
            }
        }
        
        print("\n\nMonitoring stopped by user")
    }
}

// Main entry point
let configPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "config.json"

do {
    let monitor = try DiskMonitor(configPath: configPath)
    monitor.run()
} catch {
    print("Failed to start monitor: \(error.localizedDescription)")
    exit(1)
}

