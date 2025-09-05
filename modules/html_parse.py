from bs4 import BeautifulSoup
from markdown import markdown
import re


def extract_id(html_element):
    soup = BeautifulSoup(html_element, 'html.parser')
    element = soup.find(True, id=True)
    return element['id'] if element and 'id' in element.attrs else ''


def md_to_html(md_text):
    # Replace tabs and newlines
    html_text = md_text.replace(r'\t', '<span class="margin"></span>')
    html_text = html_text.replace(r'\n', '<br>')
    html_text = html_text.replace('\n', '\n\n')

    # Adjust pattern to capture the full query string if it exists for YouTube links
    youtube_pattern = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})(\?[\w=&-]*)?)'

    def replace_youtube(match):
        video_id = match.group(2)
        query_params = match.group(3) if match.group(3) else ''
        return (
            f'<div style="display: flex; justify-content: center;">'
            f'  <div class="yt-embed">'
            f'    <iframe title="YouTube video player" '
            f'            src="https://www.youtube.com/embed/{video_id}{query_params}" '
            f'            style="width: 100%; height: 100%; border: 0;" '
            f'            allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            f'            gyroscope; picture-in-picture; web-share" allowfullscreen '
            f'            referrerpolicy="strict-origin-when-cross-origin"></iframe>'
            f'  </div>'
            f'</div>'
        )

    # Substitute YouTube links with embedded players
    html_text = re.sub(youtube_pattern, replace_youtube, html_text)

    # Detect image pattern and multiple class names after it
    img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)\s*((?:\.\w[\w-]*\s*)*)'  # Captures alt, URL, and classes on the same line

    def replace_image(match):
        alt_text = match.group(1)  # Alt text
        img_url = match.group(2)  # Image URL
        classes = match.group(3)  # Optional classes on the same line

        # Extract all class names from the same line
        class_names = ' '.join(re.findall(r'\.(\w[\w-]*)', classes)) if classes else ''
        class_attr = f' class="{class_names}"' if class_names else ''

        # Ensure there's a newline after the image HTML
        return f'<img loading="lazy" src="{img_url}" alt="{alt_text}"{class_attr}>\n\n'

    # Replace image markdown with HTML
    html_text = re.sub(img_pattern, replace_image, html_text)

    return markdown(html_text)
