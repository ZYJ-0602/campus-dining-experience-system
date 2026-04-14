import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app import app, db
from models import EvaluationMain
from app import _analyze_evaluation_sentiment, _recommendation_ctr_significance, _recommendation_ab_summary


def build_sentiment_report(campus_id=1, days=7, canteen_id=0, limit=10):
    start_time = datetime.now() - timedelta(days=max(1, int(days)))
    query = EvaluationMain.query.filter(
        EvaluationMain.campus_id == campus_id,
        EvaluationMain.create_time >= start_time,
    )
    if canteen_id:
        query = query.filter(EvaluationMain.canteen_id == canteen_id)

    rows = query.order_by(EvaluationMain.create_time.desc(), EvaluationMain.id.desc()).all()

    label_counter = Counter()
    risk_counter = Counter()
    trend_map = {}
    samples = []

    for row in rows:
        sentiment = _analyze_evaluation_sentiment(row)
        label = sentiment.get('label', 'neutral')
        risk_level = sentiment.get('risk_level', 'low')
        label_counter[label] += 1
        risk_counter[risk_level] += 1

        day_key = row.create_time.strftime('%Y-%m-%d') if row.create_time else datetime.now().strftime('%Y-%m-%d')
        day_slot = trend_map.setdefault(day_key, {'date': day_key, 'total': 0, 'negative': 0, 'risk_high': 0})
        day_slot['total'] += 1
        if label == 'negative':
            day_slot['negative'] += 1
        if risk_level == 'high':
            day_slot['risk_high'] += 1

        if label == 'negative' or risk_level == 'high':
            samples.append(
                {
                    'evaluation_id': int(row.id or 0),
                    'create_time': row.create_time.strftime('%Y-%m-%d %H:%M:%S') if row.create_time else '-',
                    'canteen_id': int(row.canteen_id or 0),
                    'window_id': int(row.window_id or 0),
                    'comprehensive_score': round(float(row.comprehensive_score or 0.0), 2),
                    'sentiment_score': float(sentiment['sentiment_score']),
                    'risk_score': float(sentiment['risk_score']),
                    'risk_level': risk_level,
                    'label': label,
                    'remark_excerpt': (str(row.remark or '').strip()[:80] or '-'),
                    'keyword_hits': sentiment.get('keyword_hits', {}),
                }
            )

    samples.sort(key=lambda item: (item['risk_score'], 1 - item['sentiment_score'], -item['comprehensive_score']), reverse=True)

    total = len(rows)
    summary = {
        'campus_id': campus_id,
        'canteen_id': canteen_id,
        'days': days,
        'total': total,
        'summary': {
            'positive': int(label_counter['positive']),
            'neutral': int(label_counter['neutral']),
            'negative': int(label_counter['negative']),
            'negative_ratio': round(float(label_counter['negative'] / total), 4) if total else 0.0,
            'risk': {
                'low': int(risk_counter['low']),
                'medium': int(risk_counter['medium']),
                'high': int(risk_counter['high']),
            },
        },
        'trend': [trend_map[key] for key in sorted(trend_map.keys())],
        'high_risk_samples': samples[:limit],
    }
    return summary


def build_recommendation_report(campus_id=1, days=7, page=''):
    summary, rows = _recommendation_ab_summary(campus_id, days=days, page=page)
    by_variant = {item['variant']: item for item in summary}
    significance = _recommendation_ctr_significance(
        by_variant.get('A', {}).get('click', 0),
        by_variant.get('A', {}).get('exposure', 0),
        by_variant.get('B', {}).get('click', 0),
        by_variant.get('B', {}).get('exposure', 0),
    )
    return {
        'campus_id': campus_id,
        'days': days,
        'page': page or 'all',
        'summary': summary,
        'significance': significance,
        'total_events': len(rows),
    }


def build_result_tables(sentiment_report, recommendation_report):
    sentiment_rows = []
    summary = sentiment_report.get('summary', {})
    sentiment_rows.append(['正面', summary.get('positive', 0)])
    sentiment_rows.append(['中性', summary.get('neutral', 0)])
    sentiment_rows.append(['负面', summary.get('negative', 0)])
    sentiment_rows.append(['负面占比', f"{summary.get('negative_ratio', 0.0) * 100:.2f}%"])
    for key, value in (summary.get('risk') or {}).items():
        sentiment_rows.append([f'风险_{key}', value])

    recommendation_rows = []
    for row in recommendation_report.get('summary', []):
        recommendation_rows.append([
            row.get('variant', '-'),
            row.get('exposure', 0),
            row.get('click', 0),
            f"{row.get('ctr', 0.0):.2f}%",
        ])
    sig = recommendation_report.get('significance', {})
    recommendation_rows.append(['z_score', sig.get('z_score', 0)])
    recommendation_rows.append(['p_value', sig.get('p_value', 1)])
    recommendation_rows.append(['significant', sig.get('significant', False)])

    return {
        'sentiment_table': sentiment_rows,
        'recommendation_table': recommendation_rows,
    }


def render_markdown_table(headers, rows):
    if not rows:
        return ''
    header_line = '| ' + ' | '.join(headers) + ' |'
    divider_line = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
    body_lines = []
    for row in rows:
        body_lines.append('| ' + ' | '.join(str(item) for item in row) + ' |')
    return '\n'.join([header_line, divider_line, *body_lines])


def render_markdown(sentiment_report, recommendation_report):
    tables = build_result_tables(sentiment_report, recommendation_report)
    lines = []
    lines.append('# 校园餐饮智能分析报告')
    lines.append('')
    lines.append('## 1. 情感分析总览')
    lines.append(f"- 校区ID: {sentiment_report['campus_id']}")
    lines.append(f"- 统计窗口: 近{sentiment_report['days']}天")
    lines.append(f"- 数据量: {sentiment_report['total']}")
    lines.append(
        f"- 情感分布: 正面 {sentiment_report['summary']['positive']} / 中性 {sentiment_report['summary']['neutral']} / 负面 {sentiment_report['summary']['negative']}"
    )
    lines.append(f"- 负面占比: {sentiment_report['summary']['negative_ratio'] * 100:.2f}%")
    lines.append('')
    lines.append('### 日趋势')
    for item in sentiment_report['trend']:
        lines.append(
            f"- {item['date']}: 总量 {item['total']} / 负面 {item['negative']} / 高风险 {item['risk_high']}"
        )
    lines.append('')
    lines.append('### 高风险样本')
    for item in sentiment_report['high_risk_samples'][:10]:
        lines.append(
            f"- #{item['evaluation_id']} 风险{item['risk_level']} 评分{item['comprehensive_score']:.1f} 备注: {item['remark_excerpt']}"
        )
    lines.append('')
    lines.append('### 结果表模板')
    lines.append(render_markdown_table(['指标', '数值'], tables['sentiment_table']))

    lines.append('')
    lines.append('## 2. 推荐实验结果')
    lines.append(f"- 校区ID: {recommendation_report['campus_id']}")
    lines.append(f"- 统计窗口: 近{recommendation_report['days']}天")
    lines.append(f"- 页面: {recommendation_report['page']}")
    lines.append(f"- 样本量: {recommendation_report['total_events']}")
    for row in recommendation_report['summary']:
        lines.append(
            f"- 组 {row['variant']}: 曝光 {row['exposure']} / 点击 {row['click']} / CTR {row['ctr']}%"
        )
    sig = recommendation_report['significance']
    lines.append(f"- 显著性: z={sig['z_score']}, p={sig['p_value']}, significant={sig['significant']}")
    lines.append('')
    lines.append('### 结果表模板')
    lines.append(render_markdown_table(['实验组', '曝光', '点击', 'CTR'], tables['recommendation_table'][:3]))
    lines.append('')
    lines.append('## 3. 论文可直接引用的对比摘要')
    lines.append('- 情感分析用于识别负面舆情并为推荐排序提供抑制信号。')
    lines.append('- 推荐实验用于比较 baseline 与 explore 两种策略的点击效果。')
    lines.append('- 两条链路在同一校园场景中共享评价与反馈数据，适合写成“多源反馈融合推荐与舆情治理”主题。')
    return '\n'.join(lines)


def export_csv_tables(output_dir, sentiment_report, recommendation_report):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    tables = build_result_tables(sentiment_report, recommendation_report)

    sentiment_csv = output_path / 'sentiment_summary.csv'
    with sentiment_csv.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['metric', 'value'])
        writer.writerows(tables['sentiment_table'])

    recommendation_csv = output_path / 'recommendation_ab_summary.csv'
    with recommendation_csv.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['variant', 'exposure', 'click', 'ctr'])
        for row in recommendation_report.get('summary', []):
            writer.writerow([
                row.get('variant', '-'),
                row.get('exposure', 0),
                row.get('click', 0),
                f"{row.get('ctr', 0.0):.2f}%",
            ])
        sig = recommendation_report.get('significance', {})
        writer.writerow([])
        writer.writerow(['z_score', sig.get('z_score', 0)])
        writer.writerow(['p_value', sig.get('p_value', 1)])
        writer.writerow(['significant', sig.get('significant', False)])

    return {
        'sentiment_csv': str(sentiment_csv),
        'recommendation_csv': str(recommendation_csv),
    }


def main():
    parser = argparse.ArgumentParser(description='生成情感分析与推荐实验报告')
    parser.add_argument('--campus-id', type=int, default=1)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--canteen-id', type=int, default=0)
    parser.add_argument('--page', type=str, default='')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--output', type=str, default='')
    parser.add_argument('--format', type=str, default='md', choices=['md', 'json'])
    parser.add_argument('--export-csv-dir', type=str, default='')
    args = parser.parse_args()

    with app.app_context():
        sentiment_report = build_sentiment_report(
            campus_id=args.campus_id,
            days=args.days,
            canteen_id=args.canteen_id,
            limit=args.limit,
        )
        recommendation_report = build_recommendation_report(
            campus_id=args.campus_id,
            days=args.days,
            page=args.page,
        )
        payload = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'sentiment': sentiment_report,
            'recommendation': recommendation_report,
            'result_tables': build_result_tables(sentiment_report, recommendation_report),
        }

        if args.format == 'json':
            rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            rendered = render_markdown(sentiment_report, recommendation_report)

        if args.export_csv_dir:
            csv_info = export_csv_tables(args.export_csv_dir, sentiment_report, recommendation_report)
            if args.format == 'json':
                payload['csv_exports'] = csv_info

        if args.output:
            Path(args.output).write_text(rendered, encoding='utf-8')
        else:
            print(rendered)


if __name__ == '__main__':
    main()
