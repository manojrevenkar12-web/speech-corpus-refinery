import { describe, expect, it } from "vitest";

import { count, duration, fileOf, hostOf, pct, seconds, usd } from "./format";
import { reasonOf } from "./reasons";

describe("format", () => {
  it("writes durations, money and shares for people", () => {
    expect(duration(0.0005)).toBe("2 s");
    expect(duration(0.036)).toBe("2.2 min");
    expect(duration(3.25)).toBe("3.3 h");
    expect(seconds(65.2)).toBe("1:05");
    expect(seconds(7.71)).toBe("7.7 s");
    expect(usd(null)).toBe("nothing kept");
    expect(usd(0.0583)).toBe("$0.06");
    expect(usd(0.0021)).toBe("$0.0021");
    expect(pct(0.605)).toBe("61%");
    expect(hostOf("http://a.example/x/y.mp3")).toBe("a.example");
    expect(fileOf("http://a.example/x/y.mp3")).toBe("y.mp3");
    expect(count(1, "file")).toBe("1 file");
    expect(count(1200, "file")).toBe("1,200 files");
  });

  it("names every reason, including segment-level ones", () => {
    expect(reasonOf(null).label).toBe("Kept");
    expect(reasonOf("tdm").family).toBe("rights");
    expect(reasonOf("segments:noise").label).toBe("Too noisy (segments)");
    expect(reasonOf("something_new").label).toBe("something new");
  });
});
