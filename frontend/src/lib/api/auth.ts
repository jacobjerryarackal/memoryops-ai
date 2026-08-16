import {
    setAccessToken,
    clearAccessToken,
} from "./client";

const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000";

interface LoginResponse {
    access_token: string;
    token_type: string;
    expires_in: number;
}

export async function login(
    username: string,
    password: string
): Promise<LoginResponse> {
    const res = await fetch(`${API_BASE_URL}/api/auth/token`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            username,
            password,
        }),
    });

    if (!res.ok) {
        let message = "Login failed";

        try {
            const body = await res.json();

            if (body?.detail) {
                message = body.detail;
            }
        } catch {
            // ignore
        }

        throw new Error(message);
    }

    const data: LoginResponse = await res.json();

    setAccessToken(data.access_token);

    return data;
}

export function logout(): void {
    clearAccessToken();
}