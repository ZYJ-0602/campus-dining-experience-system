from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app, db, _ensure_schema_columns
from models import Note, SensitiveWord, User
from seed_defaults import ensure_default_admin_operator_accounts


DEFAULT_CAMPUS_ID = 1
DEFAULT_PASSWORD = '123456'


DEMO_AUTHORS = [
    {
        'username': 'demo_writer_01',
        'nickname': '北区观察员',
        'role': 'student',
    },
    {
        'username': 'demo_writer_02',
        'nickname': '午餐测评员',
        'role': 'student',
    },
    {
        'username': 'demo_writer_03',
        'nickname': '食堂体验官',
        'role': 'teacher',
    },
]


DEMO_NOTES = [
    {
        'slug': 'north-red-braised-pork',
        'author_username': 'demo_writer_01',
        'title': '北区一食堂午餐实录：红烧肉软烂入味，米饭香气很足',
        'content': (
            '今天中午在北区一食堂试了红烧肉套餐。\n\n'
            '![北区午餐实拍](/static/img/food-hero.jpg)\n\n'
            '肉块炖得比较透，咸甜口平衡，米饭颗粒分明。\n'
            '窗口阿姨提醒大家按顺序取餐，整体排队节奏还可以。\n\n'
            '这篇用于校园餐饮系统的真实演示，不是占位文本。'
        ),
        'status': 'published',
        'like_count': 128,
        'hours_ago': 8,
    },
    {
        'slug': 'south-tomato-egg',
        'author_username': 'demo_writer_02',
        'title': '南区二食堂番茄炒蛋：火候稳定，汤汁拌饭很好吃',
        'content': (
            '晚饭去南区二食堂吃了番茄炒蛋，配的是小份青菜和紫菜汤。\n\n'
            '![番茄炒蛋](/static/img/note-cover-2.svg)\n\n'
            '番茄酸甜度适中，鸡蛋没有过老，适合想吃清淡一点的人。\n'
            '我个人觉得这一餐性价比不错，建议饭点稍早一点去。'
        ),
        'status': 'published',
        'like_count': 94,
        'hours_ago': 18,
    },
    {
        'slug': 'west-noodle-new-item',
        'author_username': 'demo_writer_03',
        'title': '西区面食窗口新品：牛肉面汤头清爽，面量很足',
        'content': (
            '今天试了西区面食窗口的牛肉面，新品上线后分量明显更实在。\n\n'
            '![牛肉面新品](/static/img/note-cover-3.svg)\n\n'
            '汤头偏清爽，不会特别重油，牛肉片给得也比较大方。\n'
            '如果后续能再增加一点配菜层次，会更适合长期回购。'
        ),
        'status': 'published',
        'like_count': 176,
        'hours_ago': 30,
    },
    {
        'slug': 'window-service-pending',
        'author_username': 'demo_writer_01',
        'title': '窗口服务反馈：提醒餐具回收时语气可以再温和一点',
        'content': (
            '今天打饭的时候，窗口工作人员效率不错，但是提醒回收餐具时语气稍微有点急。\n\n'
            '![服务场景](/static/img/hero-bg.jpg)\n\n'
            '整体还是正常的校园食堂体验，建议在高峰期多安排一位分流人员。'
        ),
        'status': 'pending',
        'like_count': 12,
        'hours_ago': 5,
    },
    {
        'slug': 'food-safety-review-pending',
        'author_username': 'demo_writer_02',
        'title': '食安提醒：台面清洁到位，但公示信息还可以更完整',
        'content': (
            '这条是用于审核流程演示的真实内容样例。\n\n'
            '![食安公示](/static/img/note-cover-4.svg)\n\n'
            '后厨台面看起来比较整洁，不过如果能把当日公示、食材来源和留样说明写得更清楚，会更安心。'
        ),
        'status': 'pending',
        'like_count': 8,
        'hours_ago': 2,
    },
    {
        'slug': 'rejected-short-note',
        'author_username': 'demo_writer_03',
        'title': '内容过短的示例笔记：需要补充更多细节',
        'content': (
            '这是一条用于审核驳回场景的示例笔记。\n\n'
            '![示例封面](/static/img/food-hero.jpg)\n\n'
            '内容太短，系统审核时可以直接作为驳回样本。'
        ),
        'status': 'rejected',
        'like_count': 3,
        'hours_ago': 48,
    },
]


DEMO_SENSITIVE_WORDS = [
    '过期',
    '变质',
    '发霉',
    '异物',
    '头发',
    '苍蝇',
    '油耗子',
    '餐具脏',
    '卫生差',
    '口水',
    '塑料片',
    '拉群',
    '加微信',
    '广告',
    '辱骂',
]


REPAIR_TEMPLATES = {
    'published': [
        {
            'title': '北区食堂午餐记录：红烧肉套餐口味稳定',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的北区封面](/static/img/note-cover-1.svg)\n\n'
                '红烧肉炖得比较烂，肥瘦比例合适，整体口味偏家常。\n'
                '作为校园餐饮系统的演示数据，这条记录用于展示正常发布内容。'
            ),
        },
        {
            'title': '南区食堂晚餐分享：番茄炒蛋很下饭',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的南区封面](/static/img/note-cover-2.svg)\n\n'
                '番茄炒蛋酸甜合适，配米饭很好下饭，适合大多数同学口味。'
            ),
        },
        {
            'title': '西区窗口体验：牛肉面分量充足，汤头清爽',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的西区封面](/static/img/note-cover-3.svg)\n\n'
                '牛肉面份量实在，汤头清爽，适合赶时间的午餐选择。'
            ),
        },
    ],
    'pending': [
        {
            'title': '窗口服务反馈：提醒餐具回收时语气可以再温和一点',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的服务场景](/static/img/hero-bg.jpg)\n\n'
                '今天打饭的时候，窗口工作人员效率不错，但是提醒回收餐具时语气稍微有点急。'
            ),
        },
        {
            'title': '食安提醒：台面清洁到位，但公示信息还可以更完整',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的食安公示](/static/img/note-cover-4.svg)\n\n'
                '后厨台面看起来比较整洁，不过如果能把当日公示、食材来源和留样说明写得更清楚，会更安心。'
            ),
        },
    ],
    'rejected': [
        {
            'title': '内容过短的示例笔记：需要补充更多细节',
            'content': (
                '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
                '![修复后的示例封面](/static/img/food-hero.jpg)\n\n'
                '内容太短，系统审核时可以直接作为驳回样本。'
            ),
        },
    ],
}


def _get_or_create_author(item):
    row = User.query.filter_by(username=item['username']).first()
    if row:
        changed = False
        if row.nickname != item['nickname']:
            row.nickname = item['nickname']
            changed = True
        if row.role != item['role']:
            row.role = item['role']
            changed = True
        if getattr(row, 'campus_id', DEFAULT_CAMPUS_ID) != DEFAULT_CAMPUS_ID:
            row.campus_id = DEFAULT_CAMPUS_ID
            changed = True
        if changed:
            db.session.commit()
        return row

    row = User(
        username=item['username'],
        password=generate_password_hash(DEFAULT_PASSWORD),
        role=item['role'],
        campus_id=DEFAULT_CAMPUS_ID,
        nickname=item['nickname'],
    )
    db.session.add(row)
    db.session.flush()
    return row


def _looks_broken_text(value):
    text = str(value or '').strip()
    if not text:
        return True
    if text in {'?', '??', '???', '????', '?????', '？？', '？？？', '？？？？', '？？？？？'}:
        return True
    if text.count('?') >= max(3, len(text) // 4):
        return True
    if text.count('�') >= 1:
        return True
    return False


def _repair_broken_note(note, author_username):
    title_map = {
        'demo_writer_01': '北区食堂午餐记录：红烧肉套餐口味稳定',
        'demo_writer_02': '南区食堂晚餐分享：番茄炒蛋很下饭',
        'demo_writer_03': '西区窗口体验：牛肉面分量充足，汤头清爽',
    }
    content_map = {
        'demo_writer_01': (
            '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
            '![修复后的北区封面](/static/img/note-cover-1.svg)\n\n'
            '红烧肉炖得比较烂，肥瘦比例合适，整体口味偏家常。\n'
            '作为校园餐饮系统的演示数据，这条记录用于展示正常发布内容。'
        ),
        'demo_writer_02': (
            '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
            '![修复后的南区封面](/static/img/note-cover-2.svg)\n\n'
            '番茄炒蛋酸甜合适，配米饭很好下饭，适合大多数同学口味。'
        ),
        'demo_writer_03': (
            '原先这条笔记标题和正文存在乱码，这里已替换为可读版本。\n\n'
            '![修复后的西区封面](/static/img/note-cover-3.svg)\n\n'
            '牛肉面份量实在，汤头清爽，适合赶时间的午餐选择。'
        ),
    }

    note.title = title_map.get(author_username, '校园餐饮真实演示笔记')
    note.content = content_map.get(author_username, '这是一条已修复的真实演示笔记。\n\n![演示图片](/static/img/food-hero.jpg)')
    note.status = 'published'
    note.like_count = max(int(note.like_count or 0), 20)
    note.campus_id = DEFAULT_CAMPUS_ID
    note.create_time = datetime.now() - timedelta(hours=6)


def _upsert_demo_note(item, authors):
    author = authors[item['author_username']]
    note = Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID, title=item['title']).first()
    if not note:
        note = Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID, user_id=author.id, status=item['status']).first()

    if note:
        if _looks_broken_text(note.title) or _looks_broken_text(note.content):
            _repair_broken_note(note, item['author_username'])
        else:
            note.user_id = author.id
            note.status = item['status']
            note.like_count = max(int(note.like_count or 0), item['like_count'])
            note.campus_id = DEFAULT_CAMPUS_ID
            note.create_time = datetime.now() - timedelta(hours=item['hours_ago'])
        return note, False

    note = Note(
        campus_id=DEFAULT_CAMPUS_ID,
        user_id=author.id,
        title=item['title'],
        content=item['content'],
        status=item['status'],
        like_count=item['like_count'],
        create_time=datetime.now() - timedelta(hours=item['hours_ago']),
    )
    db.session.add(note)
    db.session.flush()
    return note, True


def _repair_existing_broken_notes(authors):
    repaired = 0
    candidates = (
        Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID)
        .order_by(Note.status.asc(), Note.create_time.asc(), Note.id.asc())
        .all()
    )

    publish_templates = REPAIR_TEMPLATES['published']
    pending_templates = REPAIR_TEMPLATES['pending']
    rejected_templates = REPAIR_TEMPLATES['rejected']

    published_idx = 0
    pending_idx = 0
    rejected_idx = 0

    author_list = list(authors.values())
    if not author_list:
        return 0

    for note in candidates:
        if not (_looks_broken_text(note.title) or _looks_broken_text(note.content)):
            continue

        status = (note.status or 'published').strip().lower()
        if status not in REPAIR_TEMPLATES:
            status = 'published'

        if status == 'pending':
            template = pending_templates[pending_idx % len(pending_templates)]
            pending_idx += 1
        elif status == 'rejected':
            template = rejected_templates[rejected_idx % len(rejected_templates)]
            rejected_idx += 1
        else:
            template = publish_templates[published_idx % len(publish_templates)]
            published_idx += 1

        note.user_id = author_list[note.id % len(author_list)].id
        note.title = template['title']
        note.content = template['content']
        note.campus_id = DEFAULT_CAMPUS_ID
        note.like_count = max(int(note.like_count or 0), 20)
        if status == 'published':
            note.status = 'published'
            note.create_time = datetime.now() - timedelta(hours=4 + repaired)
        elif status == 'pending':
            note.status = 'pending'
            note.create_time = datetime.now() - timedelta(hours=2 + repaired)
        else:
            note.status = 'rejected'
            note.create_time = datetime.now() - timedelta(days=2, hours=repaired)
        repaired += 1

    return repaired


def _ensure_sensitive_words(words):
    created = 0
    for word in words:
        exists = SensitiveWord.query.filter_by(word=word).first()
        if exists:
            continue
        db.session.add(SensitiveWord(word=word))
        created += 1
    return created


def seed_real_demo_data():
    with app.app_context():
        _ensure_schema_columns()
        ensure_default_admin_operator_accounts()

        authors = {}
        for item in DEMO_AUTHORS:
            authors[item['username']] = _get_or_create_author(item)

        created_notes = 0
        repaired_notes = 0
        for item in DEMO_NOTES:
            note, created = _upsert_demo_note(item, authors)
            if created:
                created_notes += 1

        repaired_notes += _repair_existing_broken_notes(authors)

        created_words = _ensure_sensitive_words(DEMO_SENSITIVE_WORDS)
        db.session.commit()

        published_notes = Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID, status='published').count()
        pending_notes = Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID, status='pending').count()
        rejected_notes = Note.query.filter_by(campus_id=DEFAULT_CAMPUS_ID, status='rejected').count()

        print('真实演示数据补种完成')
        print(f'新增笔记: {created_notes}，修复笔记: {repaired_notes}')
        print(f'校区1统计: published={published_notes}, pending={pending_notes}, rejected={rejected_notes}')
        print(f'新增敏感词: {created_words}')


if __name__ == '__main__':
    seed_real_demo_data()