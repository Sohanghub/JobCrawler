from jobcrawler.extract import clean_text

PAGE = """
<html><head><style>.x{color:red}</style><script>track()</script></head>
<body>
  <header><a href="/">Acme</a> <nav>Home | About</nav></header>
  <div class="cookie">We use cookies. Accept?</div>
  <main>
    <h1>Backend Engineer</h1>
    <p>You will need    2-3 years of Python.</p>
    <div class="share">Share on X</div>
  </main>
  <aside class="sidebar">Other roles: Staff Engineer, 10+ years</aside>
  <footer>&copy; Acme. Careers powered by nobody.</footer>
</body></html>
"""


def test_boilerplate_is_stripped():
    text = clean_text(PAGE)
    assert "Backend Engineer" in text
    assert "2-3 years of Python" in text  # runs of whitespace collapsed
    for noise in ("track()", "color:red", "Home | About", "cookies",
                  "Share on X", "powered by nobody"):
        assert noise not in text
    # the sidebar's "10+ years" is the reason this matters: left in, it makes
    # matching.experience_ok reject a job whose own text says 2-3
    assert "10+ years" not in text


def test_main_content_preferred_over_whole_page():
    html = ("<body><div>Unrelated marketing copy</div>"
            "<article>Real posting</article></body>")
    assert clean_text(html) == "Real posting"


def test_no_main_element_falls_back_to_body():
    assert "Real posting" in clean_text("<body><div>Real posting</div></body>")


def test_limit_is_honoured():
    assert len(clean_text("<body>" + "word " * 5000 + "</body>", limit=50)) == 50


def test_garbage_input_never_raises():
    # a detail page that isn't really HTML costs one weak filter decision;
    # an exception here would cost the whole company's run
    assert clean_text("") == ""
    assert isinstance(clean_text("<<<not html"), str)
    assert isinstance(clean_text("\x00\xff binary junk"), str)
