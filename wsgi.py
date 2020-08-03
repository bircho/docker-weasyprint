#!/usr/bin/env python

import json
import os
import logging
import glob
import zipfile
from functools import wraps
from io import BytesIO
from tempfile import TemporaryDirectory

from flask import Flask, request, make_response, abort
from weasyprint import HTML, CSS

app = Flask('pdf')


def authenticate(f):
    @wraps(f)
    def checkauth(*args, **kwargs):
        if 'X_API_KEY' not in request.headers or os.environ.get('X_API_KEY') == request.headers['X_API_KEY']:
            return f(*args, **kwargs)
        else:
            abort(401)

    return checkauth


def auth():
    if app.config.from_envvar('X_API_KEY') == request.headers['X_API_KEY']:
        return True
    else:
        abort(401)


@app.route('/health')
def index():
    return 'ok'


@app.before_first_request
def setup_logging():
    logging.addLevelName(logging.DEBUG, "\033[1;36m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
    logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName(logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)


@app.route('/')
def home():
    return '''
            <h1>PDF Generator</h1>
            <p>The following endpoints are available:</p>
            <ul>
                <li>POST to <code>/pdf?filename=myfile.pdf</code>. The body should
                    contain html or a JSON list of html strings and css strings: { "html": html, "css": [css-file-objects] }</li>
                <li>POST to <code>/multiple?filename=myfile.pdf</code>. The body
                    should contain a JSON list of html strings. They will each
                    be rendered and combined into a single pdf</li>
                <li>POST to <code>/zip2pdf?filename=myfile.pdf</code>. The body
                    should contain a .zip file with at least one html file. Can
                    be used for image heavy pages.</li>
            </ul>
        '''


@app.route('/pdf', methods=['POST'])
@authenticate
def generate():
    name = request.args.get('filename', 'unnamed.pdf')
    app.logger.info('POST  /pdf?filename=%s' % name)
    if request.headers['Content-Type'] == 'application/json':
        data = json.loads(request.data.decode('utf-8'))
        html = HTML(string=data['html'])
        css = [CSS(string=sheet) for sheet in data['css']]
        pdf = html.write_pdf(stylesheets=css)
    else:
        html = HTML(string=request.data.decode('utf-8'))
        pdf = html.write_pdf()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline;filename=%s' % name
    app.logger.info(' ==> POST  /pdf?filename=%s  ok' % name)
    return response


@app.route('/multiple', methods=['POST'])
@authenticate
def multiple():
    name = request.args.get('filename', 'unnamed.pdf')
    app.logger.info('POST  /multiple?filename=%s' % name)
    htmls = json.loads(request.data.decode('utf-8'))
    documents = [HTML(string=html).render() for html in htmls]
    pdf = documents[0].copy([page for doc in documents for page in doc.pages]).write_pdf()
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline;filename=%s' % name
    app.logger.info(' ==> POST  /multiple?filename=%s  ok' % name)
    return response


@app.route('/zip2pdf', methods=['POST'])
@authenticate
def zip2pdf():
    name = request.args.get('filename', 'unnamed.pdf')
    app.logger.info('POST  /zip2pdf?filename=%s' % name)
    with TemporaryDirectory(prefix='weasyprint-') as temp_dir:
        with zipfile.ZipFile(BytesIO(request.data), mode='r') as myzip:
            myzip.extractall(temp_dir)
        htmls = glob.glob(os.path.join(temp_dir, '**/*.html'), recursive=True)
        csss = glob.glob(os.path.join(temp_dir, '**/*.css'), recursive=True)
        if len(htmls) == 0:
            app.logger.warning('Zip archive contain no html files.')
            abort(400)
        elif len(htmls) == 1:
            html = HTML(filename=htmls[0])
            css = [CSS(filename=sheet) for sheet in csss]
            pdf = html.write_pdf(stylesheets=css)
        else:
            documents = [HTML(filename=html).render() for html in htmls]
            pdf = documents[0].copy([page for doc in documents for page in doc.pages]).write_pdf()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline;filename=%s' % name
    app.logger.info(' ==> POST  /zip2pdf?filename=%s  ok' % name)
    return response


if __name__ == '__main__':
    app.run()
