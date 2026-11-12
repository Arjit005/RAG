import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL =
  process.env.BACKEND_INTERNAL_URL && process.env.BACKEND_INTERNAL_URL.startsWith('http')
    ? process.env.BACKEND_INTERNAL_URL
    : process.env.BACKEND_INTERNAL_URL
    ? `http://${process.env.BACKEND_INTERNAL_URL}`
    : process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function forwardRequest(req: NextRequest, method: string) {
  const url = new URL(req.url);
  // Strip '/api/proxy' and target backend '/api'
  const path = url.pathname.replace(/^\/api\/proxy/, '/api');
  const targetUrl = `${BACKEND_URL}${path}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((val, key) => {
    if (key !== 'host' && key !== 'content-length') {
      headers.set(key, val);
    }
  });

  // Extract auth token from HttpOnly cookie if present
  const sessionCookie = req.cookies.get('rag_session');
  if (sessionCookie && !headers.has('authorization')) {
    headers.set('authorization', `Bearer ${sessionCookie.value}`);
  }

  const options: RequestInit = {
    method,
    headers,
  };

  if (method !== 'GET' && method !== 'HEAD') {
    const contentType = req.headers.get('content-type') || '';
    if (contentType.includes('multipart/form-data')) {
      options.body = await req.formData();
    } else {
      options.body = await req.text();
    }
  }

  try {
    const backendRes = await fetch(targetUrl, options);

    // If logging in, capture Bearer token and set secure HttpOnly cookie
    if (path === '/api/auth/token' && backendRes.ok) {
      const data = await backendRes.json();
      const res = NextResponse.json(data);
      if (data.access_token) {
        res.cookies.set({
          name: 'rag_session',
          value: data.access_token,
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          path: '/',
          maxAge: 60 * 60 * 24, // 24 hours
        });
      }
      return res;
    }

    // Handle SSE streaming
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
