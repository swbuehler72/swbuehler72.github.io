---
layout: page
title: Tags
permalink: /tags/
---

{% assign tags = site.tags | sort %}

<div class="tags-index">
  {% for tag in tags %}
    <a href="#{{ tag[0] | slugify }}" class="tag">{{ tag[0] }} <span>({{ tag[1].size }})</span></a>
  {% endfor %}
</div>

<hr style="margin: 3rem 0; border: 0; border-top: 1px solid #eee;">

{% for tag in tags %}
  <section id="{{ tag[0] | slugify }}">
    <h2 class="year">{{ tag[0] }}</h2>
    <ul class="post-list">
      {% for post in tag[1] %}
        <li class="post-item">
          <span class="post-date">{{ post.date | date: "%b %d, %Y" }}</span>
          <span class="post-title">
            <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
          </span>
        </li>
      {% endfor %}
    </ul>
  </section>
{% endfor %}
