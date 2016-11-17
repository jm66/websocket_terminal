import eventlet
eventlet.monkey_patch()
import eventlet.websocket
import eventlet.green.socket
import eventlet.wsgi
from flask import Flask, request, redirect
import os
import urllib.parse
from wspty import EchoTerminal, SshTerminal, SocketTerminal, WebsocketBinding, EncodedTerminal
import wspty.pipe

app = Flask(__name__)
app.static_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
print("Serving static files from: " + app.static_folder)


@app.route('/')
def index():
    newurl = b'/static/index.html'
    if request.query_string:
        newurl = newurl + b'?' + request.query_string
    return redirect(newurl)


def create_terminal(obj):
    kind = obj['kind']
    hostname = obj.get('hostname', 'localhost')
    port = int(obj.get('port', '22'))
    username = obj.get('username')
    password = obj.get('password')
    term = obj.get('term')
    encoding = obj.get('encoding', 'utf8')
    def _raw():
        if kind == 'ssh':
            return SshTerminal.SshTerminal(hostname, port, username, password, term)
        if kind == 'raw':
            sock = eventlet.green.socket.socket()
            ip = eventlet.green.socket.gethostbyname(hostname)
            sock.connect((ip, port))
            return SocketTerminal.SocketTerminal(sock)
        if kind == 'echo':
            return EchoTerminal.EchoTerminal()
        raise NotImplemented('kind: %s' % kind)
    return kind, EncodedTerminal.EncodedTerminal(_raw(), encoding)


@eventlet.websocket.WebSocketWSGI
def handle_wssh(ws):
    app.logger.debug('Creating terminal with remote {remote}'.format(
        remote=ws.environ.get('REMOTE_ADDR'),
    ))

    binding = WebsocketBinding.WebsocketBinding(ws)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(ws.environ.get('QUERY_STRING', '')).items()}
    try:
        kind, terminal = create_terminal(query)
        binding.send('Connected to %s\r\n' % (kind,))
        wspty.pipe.pipe(binding, terminal)
    except BaseException as e:
        binding.send_error(e)
        raise

    return ''


def root_app(env, *args):
    route = env["PATH_INFO"]
    if route == '/wssh':
        return handle_wssh(env, *args)
    else:
        return app(env, *args)


def make_parser():
    import argparse
    parser = argparse.ArgumentParser(description='Websocket Terminal server')
    parser.add_argument('-l', default='', help='Listen on interface (default all)')
    parser.add_argument('-p', default=5002, type=int, help='Listen on port')
    return parser


def main():
    args = make_parser().parse_args()
    conn = (args.l, args.p)
    listener = eventlet.listen(conn)
    print('listening on {0}:{1}'.format(*conn))
    try:
        eventlet.wsgi.server(listener, root_app)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()