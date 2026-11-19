from copy import deepcopy
from fieldnotes.schema import parse_response, validate_document, usable_date
from fieldnotes.provider import completion
from fieldnotes.prompt import POLICY, build_prompt
from fieldnotes.storage import encoded
from .helpers import Workspace, document, rich_document, field, response


class SchemaTests(Workspace):
    def setUp(self):
        super().setUp(); self.ids=['img_one','img_two']; self.doc=rich_document(self.ids)
    def test_multiple_entries_have_separate_numbers_and_localities(self):
        errors,reasons=validate_document(self.doc,self.ids)
        self.assertEqual(errors,[]); self.assertEqual(reasons,[])
        self.assertEqual([n['value'] for n in self.doc['identifiers']],['0012','9846'])
        self.assertEqual([n['entry_id'] for n in self.doc['localities']],['north','south'])
    def test_missing_numbers_species_and_dates_are_valid(self):
        self.assertEqual(validate_document(document(self.ids),self.ids),([],[]))
    def test_locality_heading_not_forced_into_taxon(self):
        doc=document(self.ids); doc['pages'][0]['text']='North valley (0012) ♂'
        self.assertEqual(validate_document(doc,self.ids)[0],[])
        self.assertEqual(doc['taxa'],[])
    def test_author_uncertainty_distinct_from_reading_uncertainty(self):
        taxon=self.doc['taxa'][0]; taxon.update(value='Example bird?',source_uncertain=True,alternative_group='a')
        self.doc['taxa'].append(dict(taxon,value='Another bird?',normalized='Another bird'))
        self.doc['pages'][0]['text']+=' Example bird? or Another bird? [uncertain: word]'
        errors,reasons=validate_document(self.doc,self.ids)
        self.assertFalse(errors); self.assertTrue(any('author identification' in r for r in reasons))
        self.assertTrue(any('uncertain, illegible' in r for r in reasons))
    def test_prefix_suffix_range_and_zero_numbers_remain_strings(self):
        for value in ['0012','12a','E 12','12–15','12 or 17','[uncertain: 8085]']:
            doc=document(self.ids);doc['pages'][0]['text']+=value
            doc['identifiers']=[field(value,self.ids[0],number_type='unknown',namespace=None)]
            parsed,errors,_=parse_response(encoded(doc).decode(),self.ids)
            self.assertFalse(errors);self.assertEqual(parsed['identifiers'][0]['value'],value)
    def test_number_types_do_not_accept_elevation(self):
        self.doc['identifiers'][0]['number_type']='elevation'
        self.assertTrue(validate_document(self.doc,self.ids)[0])
    def test_partial_dates_supported_without_invented_precision(self):
        for written,norm,precision in [('March','--03','month_only'),('1901','1901','year'),('May 1901','1901-05','month'),('1901-05-03','1901-05-03','day'),('1901 to 1903','1901/1903','range')]:
            item=dict(value=written,normalized=norm,precision=precision,certainty='explicit')
            self.assertEqual(usable_date(item),norm)
    def test_invalid_or_two_digit_date_proposal_not_used(self):
        for written,norm,precision in [('May 99','1899-05','month'),('1901','1901-02-29','day'),('March','1901-03-01','day'),('March','--15','month_only'),('1903 to 1901','1903/1901','range')]:
            self.assertIsNone(usable_date(dict(value=written,normalized=norm,precision=precision,certainty='explicit')))
    def test_invalid_date_is_review_reason_not_retry(self):
        self.doc['dates'][0].update(normalized='1901-03-01',precision='day')
        errors,reasons=validate_document(self.doc,self.ids)
        self.assertFalse(errors);self.assertTrue(any('unsupported date' in r for r in reasons))
    def test_valid_calendar_day_cannot_add_unwritten_precision(self):
        for raw, normalized in [("1901", "1901-01-01"), ("March 1901", "1901-03-01"), ("03/04/1901", "1901-03-04")]:
            self.assertIsNone(usable_date(dict(value=raw, normalized=normalized, precision="day", certainty="explicit")))
        self.assertEqual(usable_date(dict(value="3 de marzo de 1901", normalized="1901-03-03", precision="day", certainty="explicit")), "1901-03-03")
    def test_page_coverage_order_duplicates_and_empty(self):
        for pages in [self.doc['pages'][:1],list(reversed(self.doc['pages'])),[self.doc['pages'][0]]*2]:
            self.assertTrue(validate_document(dict(self.doc,pages=pages),self.ids)[0])
        self.doc['pages'][0]['text']='';self.assertTrue(validate_document(self.doc,self.ids)[0])
    def test_blank_unrelated_cropped_and_unicode_marks_retained(self):
        for status,text in [('blank','[blank]'),('unrelated','Other material ♀ ♂ ½'),('cropped','[cropped: continued]'),('text','[deleted: old] [inserted: new] [underlined: heading] [ruled line]')]:
            doc=document(self.ids);doc['pages'][0].update(status=status,text=text)
            parsed,errors,_=parse_response(encoded(doc).decode(),self.ids)
            self.assertFalse(errors);self.assertEqual(parsed['pages'][0]['text'],text)
    def test_evidence_wrong_page_and_section_fail(self):
        for evidence in [[dict(image_id='absent',quote='0012')],[dict(image_id='img_two',entry_id='north',quote='0012')],[dict(image_id='img_one',entry_id='south',quote='0012')],[dict(image_id='img_one',entry_id='absent',location='top')]]:
            doc=deepcopy(self.doc);doc['identifiers'][0]['evidence']=evidence
            self.assertTrue(validate_document(doc,self.ids)[0])
    def test_nonverbatim_evidence_is_reviewable(self):
        self.doc['identifiers'][0]['evidence'][0]['quote']='different reading'
        errors,reasons=validate_document(self.doc,self.ids)
        self.assertFalse(errors);self.assertTrue(any('not found verbatim' in r for r in reasons))
    def test_location_only_evidence_supported(self):
        self.doc['identifiers'][0]['evidence']=[dict(image_id='img_one',entry_id='north',location='Top left, first parenthesized number')]
        self.assertFalse(validate_document(self.doc,self.ids)[0])
    def test_malformed_and_duplicate_json_preserved(self):
        for text in ['{','{"schema_version":1,"schema_version":1}','[]','{"schema_version":1,"pages":null}','NaN']:
            self.assertTrue(parse_response(text,self.ids)[1])
    def test_service_cannot_grant_human_identity(self):
        self.doc['taxa'][0]['authority_id']='tax_fake'
        self.assertTrue(parse_response(encoded(self.doc).decode(),self.ids)[1])
    def test_provider_refusal_truncation_empty_and_thought_exclusion(self):
        for reason in ['SAFETY','MAX_TOKENS','RECITATION']:
            text,errors,retry=completion(response(self.doc,reason));self.assertTrue(text);self.assertTrue(errors);self.assertFalse(retry)
        answer=response(self.doc);answer['candidates'][0]['content']['parts'].insert(0,dict(text='hidden reasoning',thought=True))
        self.assertNotIn('hidden reasoning',completion(answer)[0]);self.assertTrue(completion({})[1])
    def test_prompt_contract_no_neighbour_inheritance_or_scan_date(self):
        for text in ['ALL supplied pages','♂','♀','two-digit years','scanner dates','neighboring files','author','[deleted:','entry_id','Instructions']:
            if text=='Instructions': continue
            self.assertIn(text,POLICY)
        self.assertIn('unknown',POLICY)
        self.assertIn('"kind": "marginal", "text":', POLICY)
        self.assertIn("Notes is an array of plain strings", POLICY)
        self.assertIn("Each entry belongs to exactly one image_id", POLICY)
