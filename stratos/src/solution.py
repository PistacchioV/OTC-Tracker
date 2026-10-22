# file solution.py
# OTEL bootstrap MUST come first — installs the global TracerProvider before
# Flask is imported so its instrumentor can wire into an untraced app.
from stratosblocks.web.otel import bootstrap_otel

bootstrap_otel()

from flask import Flask, session, Response, request
from stratosblocks.authentication.web import StratosAuth, StratosDispatcherMiddleware
from stratosblocks.web.logging import enable_logging
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import json
########### ADD YOUR OTHER IMPORTS HERE ###########
import otc_stratos

# Enable logging level. Default is ERROR but can be set to DEBUG, INFO or WARN
# e.g. enable_logging("DEBUG")
logger = enable_logging("INFO")

########### DO NOT DELETE ###########
CONTEXT_ROOT = '/76521/otc-tracker-ops-ai-citizen'

def create_app():
    flask_app = Flask(__name__)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_proto=1)
    flask_app.config['SECRET_KEY'] = "76521-singing-moose-flask"
    flask_app.config['routes_pathname_prefix'] = CONTEXT_ROOT + '/'
    flask_app.wsgi_app = StratosDispatcherMiddleware(flask_app.wsgi_app, DispatcherMiddleware(
        Response('Not Found', status=404),
        {CONTEXT_ROOT: flask_app.wsgi_app}
    ))
    return flask_app

app = create_app()

# Framework instrumentation. Flask instrumentor wires ASGI-style middleware
# into the WSGI app; RequestsInstrumentor auto-traces outbound calls.
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

stratos_auth = StratosAuth(app, 76521)

@app.before_request
def add_post_body_to_trace():
    try:
        from flask import has_request_context

        if has_request_context() and request.method == 'POST':
            span = trace.get_current_span()
            if span.is_recording():
                try:
                    post_body = request.get_json()
                    if post_body:
                        span.set_attribute('http.request.post_body', json.dumps(post_body))
                except Exception:
                    try:
                        post_data = request.get_data(as_text=True)
                        if post_data:
                            span.set_attribute('http.request.post_body', post_data)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Could not add POST body to trace: {e}")

########### DO NOT DELETE ###########

########### YOUR CODE MODIFICATIONS SHOULD GO BELOW HERE ###########

# O OTC Tracker inteiro entra no `app` acima — o mesmo objeto que o Stratos
# instrumenta, autentica e serve sob o CONTEXT_ROOT. A raiz `/` passa a ser a
# do OTC (o dashboard); a explicação está no otc_stratos.py.
otc_stratos.mount(app, stratos_auth, CONTEXT_ROOT)


@app.route('/stratos/whoami')
def stratos_whoami():
    # A rota de boas-vindas do template, mudada de endereço: é o diagnóstico de
    # "o que o Stratos diz de mim", e por isso a ponte de SSO não a intercepta.
    user = stratos_auth.user()

    if user.authorized:
        message = f"Welcome, User ID: {user.sid}, Name: {user.first_name} {user.last_name}"
    else:
        message = "You are not authorized to view this page."

    return message


########### DO NOT DELETE ###########
@app.route("/actuator/keepalive")
def health():
    return {"status": "up"}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8443, debug=False)
########### DO NOT DELETE ###########
