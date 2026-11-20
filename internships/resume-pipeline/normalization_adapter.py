"""Convert extracted fields without adding information absent from extraction."""


def normalization_input(resume):
    # The normalizer consumes skills, degree, title, and project name/skills.
    # School/year/date/duration remain available on the original Resume object;
    # none are a substitute for the normalizer's field/major/grad_year fields.
    data = resume.to_dict()
    return {key: data[key] for key in ("skills", "education", "experience", "projects")}
