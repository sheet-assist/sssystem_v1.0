class ProspectTypeConverter:
    regex = "MF|TD|TL|SS"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
