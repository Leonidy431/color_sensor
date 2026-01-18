FROM bluerobotics/blueos:latest
COPY color_fish_analyzer.py /app/
LABEL type="device-integration" tags="scientific-sensor,color-analysis"
CMD ["python", "/app/color_fish_analyzer.py"]
