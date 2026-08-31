FROM python:3.11-slim

RUN pip install uv 

WORKDIR /app
COPY . .

RUN uv pip install --system -r requirements.txt

# Streamlit serves a prebuilt index.html and offers no hook for injecting into
# <head>, so the analytics tag goes in at build time. st.markdown strips
# <script>, and st.components.v1.html would run it in a sandboxed iframe where
# it would report the iframe, not the page.
#
# The final grep is a deliberate build-time assertion: if a Streamlit upgrade
# reshapes the template, the build fails loudly instead of silently shipping
# an image with no analytics.
RUN INDEX="$(python -c 'import pathlib, streamlit; print(pathlib.Path(streamlit.__file__).parent / "static/index.html")')" \
 && sed -i 's|<head>|<head><script defer data-domain="colleges.dataturd.com" src="https://plausible.ljs.app/js/script.file-downloads.outbound-links.pageview-props.tagged-events.js"></script>|' "$INDEX" \
 && grep -q 'plausible.ljs.app' "$INDEX"

ENV PORT=8080
CMD ["./start.sh"]
