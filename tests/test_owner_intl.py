from pipeline.enrich import owner
from pipeline.enrich.enrich import clean_contact_email


def test_template_addresses_are_not_contacts():
    assert clean_contact_email("john.doe@exemple.com") is None
    assert clean_contact_email("contact@votredomaine.fr") is None
    assert clean_contact_email("jan.jansen@bakkerij.nl") is None
    assert clean_contact_email("contact@atg33.fr") == "contact@atg33.fr"


def test_owner_phrases_in_other_languages():
    text = "Qui suis-je ? Je m’appelle Kevin Front-Reigner, couvreur maçon"
    assert owner.from_website_text(text, set()) == "Kevin"
    assert owner.from_website_text("Directeur de la publication PATRICK HENRY Hébergement", set()) == "PATRICK"
    assert owner.from_website_text("Bonjour, je m’appelle Sébastien", set()) == "Sébastien"
    assert owner.from_website_text("Hola, me llamo Javier y soy fontanero", set()) == "Javier"
    assert owner.from_website_text("Eigenaar: Joost de Vries", set()) == "Joost"
    assert owner.from_website_text("Inhaber: Jürgen Maier", set()) == "Jürgen"


def test_no_name_from_ordinary_words_or_countries():
    assert owner.from_website_text("Je suis Artisan couvreur depuis 1990", set()) is None
    assert owner.find(business_name="France Couverture") is None
    assert owner.find(emails=["jerome.dupuis@gmail.com"])["first_name"] == "Jerome"
    assert owner.find(website_name="jean-pierre")["first_name"] == "Jean-Pierre"
