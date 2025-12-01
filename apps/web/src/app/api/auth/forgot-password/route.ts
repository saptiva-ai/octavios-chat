/**
 * Forgot Password Proxy Route
 *
 * Proxy endpoint for password reset requests that forwards to the backend.
 *
 * Why needed:
 * - Frontend needs to call backend forgot-password endpoint
 * - This proxy handles CORS and forwarding
 *
 * Backend endpoint: POST /api/auth/forgot-password
 */

import { NextRequest, NextResponse } from "next/server";

// Use backend URL (port 8000), not file-manager (port 8001)
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    // Parse request body
    const body = await request.json();

    // Forward request to backend
    const backendUrl = `${BACKEND_URL}/api/auth/forgot-password`;
    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    // Get response data
    const data = await response.json();

    // Return response with same status code
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Forgot password proxy error:", error);
    return NextResponse.json(
      {
        detail: "Error al procesar la solicitud de recuperación de contraseña",
      },
      { status: 500 },
    );
  }
}
