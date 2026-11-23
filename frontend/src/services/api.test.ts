import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { getErrorMessage } from "./api";

const failure = (status: number, data: unknown) =>
  new AxiosError("failed", "ERR_BAD_REQUEST", undefined, undefined, {
    status, data, statusText: "", headers: {}, config: {} as never,
  });

describe("getErrorMessage", () => {
  it("explains a network failure", () => {
    expect(getErrorMessage(new AxiosError("Network Error"))).toMatch(/cannot reach the server/i);
  });
  it("uses a string detail", () => {
    expect(getErrorMessage(failure(409, { detail: "Email is already registered" }))).toBe("Email is already registered");
  });
  it("joins validation messages and strips the pydantic prefix", () => {
    const data = { detail: [{ msg: "Value error, Password is too weak" }, { msg: "Field required" }] };
    expect(getErrorMessage(failure(422, data))).toBe("Password is too weak. Field required");
  });
  it("falls back to the status code, and to a generic message for other errors", () => {
    expect(getErrorMessage(failure(500, {}))).toBe("Request failed (500)");
    expect(getErrorMessage(new Error("boom"))).toBe("Something went wrong");
  });
});