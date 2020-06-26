{% for chartmap in site.data.index.entries %}
### Development releases: {{ chartmap[0] }}

| Release | Date | Application version |
|---------|------|---------------------|
  {% assign sortedcharts = chartmap[1] | sort: 'created' | reverse -%}
  {% for chart in sortedcharts -%}
| [{{ chart.name }}-{{ chart.version | remove_first: "v" }}]({{ chart.urls[0] }}) | {{ chart.created | date_to_rfc822 }} | {{ chart.appVersion }} |
  {% endfor %}
{% endfor %}
