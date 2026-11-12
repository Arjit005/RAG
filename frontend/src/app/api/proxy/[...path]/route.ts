import { NextRequest, NextResponse } from 'next/server';

// Render provides BACKEND_INTERNAL_URL via fromService property 'host' (e.g., 'rag-intelligence-backend:10000' or 'rag-intelligence-backend')
// If BACKEND_INTERNAL_URL is set, construct the internal private network HTTP endpoint.
function getBackendUrl(): string {
  const internal = process.env.BACKEND_INTERNAL_URL;
  if (internal) {
    if (internal.startsWith('http://') || internal.startsWith('https://')) {
      return internal.replace(/\/$/, '');
    }
    return `http://${internal.replace(/\/$/, '')}`;
  }
  const publicApi = process.env.NEXT_PUBLIC_API_URL;
  if (publicApi) {
    return publicApi.replace(/\/$/, '');
  }
  return 'http://127.0.0.1:8000';
}

const BACKEND_URL = getBackendUrl();

/**
 * Validates Origin/Referer for state-changing CSRF defense.
 */
function isValidOrigin(req: NextRequest): boolean {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    return true;
  }
  const origin = req.headers.get('origin');
  const referer = req.headers.get('referer');
  const host = req.headers.get('host');

  // Allow same-origin requests
  if (origin) {
    try {
      const originUrl = new URL(origin);
      if (originUrl.host === host) return true;
      // Also allow configured FRONTEND_URL or localhost in development
      if (process.env.FRONTEND_URL && origin === process.env.FRONTEND_URL) return true;
      if (process.env.NODE_ENV !== 'production' && (originUrl.hostname === 'localhost' || originUrl.hostname === '127.0.0.1')) {
        return true;
      }
    } catch {
      return false;
    }
  }

  if (referer) {
    try {
      const refererUrl = new URL(referer);
      if (refererUrl.host === host) return true;
    } catch {
      return false;
    }
  }

  // If both origin and referer are missing in production on a mutating request, reject
  if (process.env.NODE_ENV === 'production') {
    return false;
  }
  return true;
}

async function forwardRequest(req: NextRequest, method: string) {
  // 1. CSRF / Origin Validation for state-changing requests
  if (!isValidOrigin(req)) {
    return NextResponse.json(
      { error: 'Forbidden', detail: 'Cross-Site Request Forgery validation failed: Invalid Origin/Referer.' },
      { status: 403 }
    );
  }

  const backendUrl = getBackendUrl();
  const url = new URL(req.url);
  // Strip '/api/proxy' and forward to backend
  // Note: incoming path is like /api/proxy/api/documents or /api/proxy/documents
  let cleanPath = url.pathname.replace(/^\/api\/proxy/, '');
  if (!cleanPath.startsWith('/')) {
    cleanPath = `/${cleanPath}`;
  }
  // Ensure target path starts with /api if not already present
  if (!cleanPath.startsWith('/api')) {
    cleanPath = `/api${cleanPath}`;
  }
  const targetUrl = `${backendUrl}${cleanPath}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((val, key) => {
    // Strip host, content-length, and explicitly DROP any browser-supplied authorization header
    // so client JavaScript cannot forge or bypass HttpOnly cookie authentication
    if (key !== 'host' && key !== 'content-length' && key !== 'authorization') {
      headers.set(key, val);
    }
  });

  // 2. Extract auth token ONLY from the secure HttpOnly cookie
  const sessionCookie = req.cookies.get('rag_session');
  if (sessionCookie && sessionCookie.value) {
    headers.set('authorization', `Bearer ${sessionCookie.value}`);
  }

  const options: RequestInit = {
    method,
    headers,
  };

  if (method !== 'GET' && method !== 'HEAD') {
    const contentType = req.headers.get('content-type') || '';
    if (contentType.includes('multipart/form-data')) {
      // In Node.js fetch, passing FormData requires letting fetch set the Content-Type boundary header automatically
      headers.delete('content-type');
      options.body = await req.formData();
    } else {
      options.body = await req.text();
    }
  }

  try {
    const backendRes = await fetch(targetUrl, options);

    // 3. Intercept Login: Set JWT in HttpOnly cookie and redact raw access_token from client JSON
    if (cleanPath === '/api/auth/token' && backendRes.ok) {
      const data = await backendRes.json();
      const accessToken = data.access_token;

      // Sanitized response: Redact access_token so client-side JavaScript never sees it
      const clientSafeData = {
        authenticated: true,
        user_id: data.user_id,
        tenant_id: data.tenant_id,
        email: data.email,
        role: data.role,
        message: 'Authentication successful. Secure session cookie established.'
      };

      const res = NextResponse.json(clientSafeData);
      if (accessToken) {
        res.cookies.set({
          name: 'rag_session',
          value: accessToken,
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          path: '/',
          maxAge: 60 * 60 * 24, // 24 hours
        });
      }
      return res;
    }

    // 4. Forward SSE streaming
    if (backendRes.headers.get('content-type')?.includes('text/event-stream')) {
      return new Response(backendRes.body, {
        status: backendRes.status,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache, no-transform',
          Connection: 'keep-alive',
        },
      });
    }

    const data = await backendRes.text();
    const clientRes = new NextResponse(data, {
      status: backendRes.status,
      headers: {
        'content-type': backendRes.headers.get('content-type') || 'application/json',
      },
    });

    return clientRes;
  } catch (err: any) {
    return NextResponse.json(
      { error: 'BFF Proxy Failed to connect to Backend', detail: err.message },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest) {
  return forwardRequest(req, 'GET');
}

export async function POST(req: NextRequest) {
  return forwardRequest(req, 'POST');
}

export async function PUT(req: NextRequest) {
  return forwardRequest(req, 'PUT');
}

export async function DELETE(req: NextRequest) {
  return forwardRequest(req, 'DELETE');
}
